#!/usr/bin/env python3
"""
Image Scraper UI - Web interface for Hermes B2B Image Scraper
=============================================================
Flask app with Server-Sent Events for real-time progress.

Usage:
    python app.py                    # Start on port 8787
    python app.py --port 9090        # Custom port
"""

import argparse
import base64
import hashlib
import io
import json
import logging
import os
import queue
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from PIL import Image, ImageOps, ImageFilter

# ─── APP SETUP ────────────────────────────────────────────────────────────

app = Flask(__name__)
logger = logging.getLogger("scraper-ui")
logging.basicConfig(level=logging.INFO)

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Active jobs: job_id -> {thread, queue, status, config}
active_jobs = {}


# ─── IMAGE QUALITY ANALYSIS ──────────────────────────────────────────────

class ImageQualityChecker:
    """Evaluates image quality on multiple dimensions (0-100 score)."""

    def __init__(self, config: dict):
        self.min_resolution = config.get("min_resolution", 200)
        self.min_quality_score = config.get("min_quality_score", 40)
        self.reject_watermarks = config.get("reject_watermarks", True)
        self.reject_blurry = config.get("reject_blurry", True)
        self.min_aspect_ratio = config.get("min_aspect_ratio", 0.4)
        self.max_aspect_ratio = config.get("max_aspect_ratio", 2.5)

    def evaluate(self, data: bytes) -> dict:
        """Returns {score: 0-100, passed: bool, reasons: [...]}."""
        result = {"score": 0, "passed": False, "reasons": [], "details": {}}

        try:
            img = Image.open(io.BytesIO(data))
            img_copy = Image.open(io.BytesIO(data))
        except Exception:
            result["reasons"].append("Cannot open image")
            return result

        scores = []

        # 1. Resolution check
        w, h = img.size
        result["details"]["resolution"] = f"{w}x{h}"
        if w < self.min_resolution or h < self.min_resolution:
            result["reasons"].append(f"Too small: {w}x{h} (min {self.min_resolution}px)")
            res_score = 0
        else:
            res_score = min(100, (min(w, h) / max(self.min_resolution * 2, 400)) * 100)
        scores.append(("resolution", res_score, 0.3))

        # 2. Aspect ratio check
        aspect = w / h if h > 0 else 0
        result["details"]["aspect_ratio"] = round(aspect, 2)
        if aspect < self.min_aspect_ratio or aspect > self.max_aspect_ratio:
            result["reasons"].append(f"Bad aspect ratio: {aspect:.2f}")
            aspect_score = 20
        else:
            # Prefer square-ish images for product photos
            ideal_deviation = abs(1.0 - aspect)
            aspect_score = max(20, 100 - ideal_deviation * 80)
        scores.append(("aspect_ratio", aspect_score, 0.15))

        # 3. Sharpness / blur detection (Laplacian variance)
        if self.reject_blurry:
            try:
                gray = img_copy.convert("L")
                laplacian = gray.filter(ImageFilter.FIND_EDGES)
                import numpy as np
                arr = np.array(laplacian, dtype=float)
                variance = arr.var()
                result["details"]["sharpness"] = round(variance, 1)
                if variance < 50:
                    result["reasons"].append(f"Blurry (sharpness: {variance:.0f})")
                    sharp_score = 10
                elif variance < 200:
                    sharp_score = 40 + (variance - 50) / 150 * 40
                else:
                    sharp_score = min(100, 80 + (variance - 200) / 500 * 20)
            except ImportError:
                sharp_score = 60  # Can't check without numpy
            scores.append(("sharpness", sharp_score, 0.25))

        # 4. Color diversity (simple check for placeholder/blank images)
        try:
            small = img_copy.resize((50, 50)).convert("RGB")
            colors = small.getcolors(maxcolors=2500) or []
            unique_colors = len(colors)
            result["details"]["unique_colors"] = unique_colors
            if unique_colors < 20:
                result["reasons"].append("Too uniform (possible placeholder)")
                color_score = 10
            elif unique_colors < 100:
                color_score = 30 + (unique_colors / 100) * 40
            else:
                color_score = min(100, 70 + (unique_colors / 500) * 30)
        except Exception:
            color_score = 50
        scores.append(("color_diversity", color_score, 0.15))

        # 5. File size adequacy
        file_size = len(data)
        result["details"]["file_size_kb"] = round(file_size / 1024, 1)
        if file_size < 5000:
            result["reasons"].append(f"File too small: {file_size / 1024:.1f}KB")
            size_score = 10
        elif file_size < 20000:
            size_score = 40
        else:
            size_score = min(100, 60 + (file_size / 200000) * 40)
        scores.append(("file_size", size_score, 0.15))

        # Weighted total
        total = sum(score * weight for _, score, weight in scores)
        result["score"] = round(total)
        result["passed"] = (total >= self.min_quality_score
                            and len([r for r in result["reasons"]
                                     if "Too small" in r or "Cannot" in r]) == 0)
        result["details"]["component_scores"] = {
            name: round(score, 1) for name, score, _ in scores
        }

        return result


# ─── RELEVANCE CHECKER (CLIP) ─────────────────────────────────────────────

class RelevanceChecker:
    """
    Uses OpenCLIP to compare image content with product description.
    Lazy-loads the model on first use to avoid slowing down startup.
    Returns a similarity score 0-100.
    """

    def __init__(self, min_relevance: float = 0.20):
        self.min_relevance = min_relevance  # cosine similarity threshold
        self.model = None
        self.preprocess = None
        self.tokenizer = None
        self._loaded = False
        self._available = None

    def _load(self):
        if self._loaded:
            return
        try:
            import open_clip
            import torch
            self.torch = torch  # Store reference for use in check()

            # Use a small, fast model - ViT-B-32 is a good balance
            self.model, _, self.preprocess = open_clip.create_model_and_transforms(
                'ViT-B-32', pretrained='laion2b_s34b_b79k'
            )
            self.tokenizer = open_clip.get_tokenizer('ViT-B-32')
            self.model.eval()

            # Self-test: run a dummy inference to catch runtime errors early
            dummy_img = Image.new("RGB", (224, 224), (128, 128, 128))
            dummy_input = self.preprocess(dummy_img).unsqueeze(0)
            dummy_text = self.tokenizer(["test product"])
            with torch.no_grad():
                self.model.encode_image(dummy_input)
                self.model.encode_text(dummy_text)

            self._loaded = True
            self._available = True
            logger.info("CLIP model loaded and self-test passed")
        except Exception as e:
            logger.warning(f"CLIP not available: {type(e).__name__}: {e}")
            self._loaded = True
            self._available = False

    @property
    def available(self) -> bool:
        if self._available is None:
            self._load()
        return self._available

    def check(self, image_data: bytes, product_name: str) -> dict:
        """
        Compare image with product name using CLIP.
        Returns {score: 0-100, similarity: float, relevant: bool}
        """
        if not self.available:
            return {"score": 50, "similarity": 0.0, "relevant": True, "reason": "CLIP not available"}

        try:
            torch = self.torch

            # Prepare image
            img = Image.open(io.BytesIO(image_data)).convert("RGB")
            image_input = self.preprocess(img).unsqueeze(0)

            # Prepare text
            text_input = self.tokenizer([product_name])

            # Compute similarity
            with torch.no_grad():
                image_features = self.model.encode_image(image_input)
                text_features = self.model.encode_text(text_input)

                image_features = image_features / image_features.norm(dim=-1, keepdim=True)
                text_features = text_features / text_features.norm(dim=-1, keepdim=True)

                similarity = (image_features @ text_features.T).item()

            score = max(0, min(100, (similarity - 0.10) / 0.30 * 100))
            relevant = similarity >= self.min_relevance

            reason = ""
            if not relevant:
                reason = f"Low relevance ({similarity:.2f} < {self.min_relevance})"

            return {
                "score": round(score),
                "similarity": round(similarity, 3),
                "relevant": relevant,
                "reason": reason,
            }
        except Exception as e:
            logger.warning(f"CLIP check error for '{product_name[:30]}': {type(e).__name__}: {e}")
            import traceback
            logger.warning(traceback.format_exc())
            return {"score": 50, "similarity": 0.0, "relevant": True, "reason": f"Error: {e}"}


# Global instance (lazy loaded)
_relevance_checker = None

def get_relevance_checker(min_relevance: float = 0.20) -> RelevanceChecker:
    global _relevance_checker
    if _relevance_checker is None:
        _relevance_checker = RelevanceChecker(min_relevance)
    return _relevance_checker


# ─── SEARCH ENGINES ───────────────────────────────────────────────────────

class BingImageScraper:
    """Scrape Bing Images - no API key needed."""

    SEARCH_URL = "https://www.bing.com/images/search"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,ro;q=0.8",
        })
        self._last_call = 0

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        elapsed = time.time() - self._last_call
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        try:
            resp = self.session.get(
                self.SEARCH_URL,
                params={"q": query, "form": "HDRSC2", "first": "1",
                        "qft": "+filterui:imagesize-large"},
                timeout=15,
            )
            self._last_call = time.time()
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Bing scrape error: {e}")
            return []

        results = []
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)

        for url in urls[:max_results * 2]:
            if len(results) >= max_results:
                break
            if any(skip in url.lower() for skip in [
                'favicon', 'logo', '1x1', 'pixel', '.svg', '.gif', 'placeholder'
            ]):
                continue
            results.append({"image": url, "title": query, "source": "bing"})

        return results


class DuckDuckGoSearch:
    """DuckDuckGo image search - free, no API key."""

    def __init__(self):
        self._last_call = 0

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        elapsed = time.time() - self._last_call
        if elapsed < 4:
            time.sleep(4 - elapsed)

        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.images(
                    keywords=query, region="wt-wt", safesearch="moderate",
                    size="Large", type_image="photo", max_results=max_results,
                ))
            self._last_call = time.time()
            for r in results:
                r["source"] = "ddg"
            return results
        except Exception as e:
            logger.debug(f"DDG error: {e}")
            return []


class PexelsSearch:
    """Pexels API - 200 requests/hour, free."""

    BASE_URL = "https://api.pexels.com/v1/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Authorization"] = api_key

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        if not self.api_key:
            return []
        try:
            resp = self.session.get(
                self.BASE_URL,
                params={"query": query, "per_page": min(max_results, 15),
                        "orientation": "square"},
                timeout=15,
            )
            if resp.status_code == 429:
                time.sleep(60)
                return self.search(query, max_results)
            resp.raise_for_status()
            data = resp.json()
            results = []
            for photo in data.get("photos", []):
                src = photo.get("src", {})
                img_url = src.get("medium") or src.get("large") or src.get("original", "")
                if img_url:
                    results.append({
                        "image": img_url, "title": photo.get("alt", ""),
                        "source": "pexels",
                    })
            return results
        except Exception as e:
            logger.debug(f"Pexels error: {e}")
            return []

    @property
    def available(self):
        return bool(self.api_key)


# ─── IMAGE PROCESSING ────────────────────────────────────────────────────

def download_image(url: str, timeout: int = 8) -> bytes | None:
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if "image" not in ct and "octet-stream" not in ct:
            return None
        if len(resp.content) < 2000:
            return None
        return resp.content
    except Exception:
        return None


def download_images_parallel(urls: list[str], max_workers: int = 6) -> dict[str, bytes]:
    """Download multiple images in parallel. Returns {url: data} for successful downloads."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(download_image, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            data = future.result()
            if data:
                results[url] = data
    return results


def resize_and_pad(data: bytes, target_size: tuple[int, int],
                   bg_color: tuple = (255, 255, 255),
                   quality: int = 90,
                   remove_bg: bool = False,
                   output_format: str = "webp") -> bytes:
    """
    Process image: optional bg removal, resize with padding.
    output_format: 'webp', 'jpeg', or 'png'
    """

    if remove_bg:
        try:
            from rembg import remove as rembg_remove
            nobg = rembg_remove(data)
            img = Image.open(io.BytesIO(nobg)).convert("RGBA")
        except Exception:
            img = Image.open(io.BytesIO(data))
            img = ImageOps.exif_transpose(img)
            if img.mode != "RGBA":
                img = img.convert("RGBA")
    else:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGBA":
            img = img.convert("RGBA")

    img = ImageOps.exif_transpose(img)
    tw, th = target_size
    img.thumbnail((tw, th), Image.LANCZOS)

    # For transparent formats (webp/png with bg removal), keep RGBA
    fmt = output_format.lower()
    if fmt == "png" and remove_bg:
        result = Image.new("RGBA", target_size, (255, 255, 255, 0))
        px = (tw - img.size[0]) // 2
        py = (th - img.size[1]) // 2
        result.paste(img, (px, py), mask=img.split()[3])
    elif fmt == "webp" and remove_bg:
        result = Image.new("RGBA", target_size, (255, 255, 255, 0))
        px = (tw - img.size[0]) // 2
        py = (th - img.size[1]) // 2
        result.paste(img, (px, py), mask=img.split()[3])
    else:
        result = Image.new("RGB", target_size, bg_color)
        px = (tw - img.size[0]) // 2
        py = (th - img.size[1]) // 2
        result.paste(img, (px, py), mask=img.split()[3])

    buf = io.BytesIO()
    if fmt == "webp":
        result.save(buf, "WEBP", quality=quality, method=4)
    elif fmt == "png":
        result.save(buf, "PNG", optimize=True)
    else:  # jpeg
        if result.mode == "RGBA":
            result = result.convert("RGB")
        result.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def make_thumbnail(data: bytes, size: int = 120) -> str:
    """Create a base64 thumbnail for the UI preview."""
    try:
        img = Image.open(io.BytesIO(data))
        img.thumbnail((size, size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=75)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def url_keyword_score(url: str, product_name: str) -> float:
    """
    Score 0-1 based on how many product name keywords appear in the URL.
    e.g. url contains 'lavazza' + 'gustoso' + '1kg' for product 'Lavazza CaffeCrema Gustoso 1kg'
    """
    url_lower = url.lower().replace("-", "").replace("_", "").replace("%20", "")
    words = product_name.lower().split()
    # Filter meaningful words (skip short/common ones)
    keywords = [w for w in words if len(w) >= 3
                and w not in ("the", "and", "for", "con", "per", "din", "cafea", "produs")]

    if not keywords:
        return 0.0

    matches = sum(1 for kw in keywords if kw.replace(" ", "") in url_lower)
    return matches / len(keywords)


def sanitize_comment(denumire: str) -> str:
    s = denumire.lower().strip()
    s = (s.replace(' ', '').replace('ă', 'a').replace('â', 'a')
         .replace('î', 'i').replace('ș', 's').replace('ş', 's')
         .replace('ț', 't').replace('ţ', 't'))
    s = re.sub(r'[^a-z0-9._-]', '', s)
    return s[:80]


def hermes_filename(product_id: str, denumire: str, image_number: int,
                    fmt: str = "webp") -> str:
    comment = sanitize_comment(denumire)
    ext = {"webp": ".webp", "png": ".png", "jpeg": ".jpg"}.get(fmt.lower(), ".webp")
    return str(product_id) + "}{" + comment + "}#" + str(image_number) + ext


# ─── SCRAPER JOB ──────────────────────────────────────────────────────────

def run_scraper_job(job_id: str, products: list[dict], config: dict,
                    event_queue: queue.Queue):
    """Runs the full scraping pipeline in a background thread."""

    output_dir = OUTPUT_DIR / job_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Config
    target_size = (config.get("image_width", 200), config.get("image_height", 200))
    quality = config.get("quality", 90)
    remove_bg = config.get("remove_background", False)
    output_format = config.get("output_format", "jpeg")
    images_per_product = config.get("images_per_product", 1)
    search_suffix = config.get("search_suffix", "product photo")
    pexels_key = config.get("pexels_key", "")
    bing_key = config.get("bing_key", "")
    max_candidates = config.get("max_candidates", 10)
    # Clean priority sites: extract domain from full URLs
    raw_sites = [s.strip() for s in config.get("priority_sites", []) if s.strip()]
    priority_sites = []
    for site in raw_sites:
        # Remove protocol and path, keep only domain
        s = site.replace("https://", "").replace("http://", "")
        s = s.split("/")[0]  # Remove path
        s = s.split("?")[0]  # Remove query params
        s = s.lstrip("www.")  # Optional: remove www
        if s:
            priority_sites.append(s)

    quality_checker = ImageQualityChecker({
        "min_resolution": config.get("min_resolution", 200),
        "min_quality_score": config.get("min_quality_score", 40),
        "reject_blurry": config.get("reject_blurry", True),
        "min_aspect_ratio": config.get("min_aspect_ratio", 0.4),
        "max_aspect_ratio": config.get("max_aspect_ratio", 2.5),
    })

    def send(event_type, data):
        event_queue.put({"event": event_type, "data": data})

    # Relevance checker (CLIP)
    use_relevance = config.get("check_relevance", True)
    min_relevance = config.get("min_relevance", 0.20)
    relevance_checker = get_relevance_checker(min_relevance) if use_relevance else None

    # Pre-load CLIP model before starting (so first product isn't slow)
    if relevance_checker:
        send("status", {"message": "Loading AI relevance model (first time only)..."})
        relevance_checker._load()
        if relevance_checker.available:
            send("status", {"message": "AI relevance model ready"})
        else:
            send("status", {"message": "AI model not available, skipping relevance check"})
            relevance_checker = None

    # Init search engines
    bing_scraper = BingImageScraper()
    ddg = DuckDuckGoSearch()
    pexels = PexelsSearch(pexels_key)

    send("job_start", {
        "job_id": job_id,
        "total_products": len(products),
        "config": config,
    })

    results = []
    stats = {"total": len(products), "success": 0, "failed": 0, "images_saved": 0}

    for idx, product in enumerate(products):
        # Check if job was cancelled
        job = active_jobs.get(job_id)
        if job and job.get("status") == "cancelled":
            send("job_done", {
                "job_id": job_id, "stats": stats,
                "output_dir": str(output_dir.resolve()),
                "cancelled": True,
            })
            return

        denumire = product["denumire"].strip()
        product_id = product.get("id", str(idx + 1))

        if not denumire:
            continue

        send("product_start", {
            "index": idx,
            "total": len(products),
            "product_id": product_id,
            "denumire": denumire,
        })

        # Build search queries - multiple strategies for better results
        GREAT_RELEVANCE = 80

        # Generate query variants: exact name, with suffix, simplified
        query_variants = []
        # 1. Exact product name (best for specific products)
        query_variants.append(f'"{denumire}"')
        # 2. Product name + suffix
        query_variants.append(f"{denumire} {search_suffix}".strip())
        # 3. Simplified: remove common words, keep brand + key identifiers
        words = denumire.split()
        if len(words) > 4:
            # Keep first 4 meaningful words
            simplified = " ".join(words[:4])
            query_variants.append(f"{simplified} {search_suffix}".strip())

        # Deduplicate queries
        query_variants = list(dict.fromkeys(query_variants))

        # ── SEARCH: collect URLs from multiple queries ──
        search_urls = []  # [(url, source)]
        seen_urls = set()

        def collect(results, source):
            for r in results:
                url = r.get("image", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    search_urls.append((url, source))

        # Priority sites first
        if priority_sites:
            for site in priority_sites:
                site_query = f"site:{site} {denumire}"
                send("search_phase", {"index": idx, "phase": "priority", "site": site, "query": site_query})
                for sn, searcher in [("bing", bing_scraper), ("ddg", ddg)]:
                    try:
                        sr = searcher.search(site_query, max_results=max_candidates)
                        if sr:
                            collect(sr, f"{sn}:{site}")
                            break
                    except Exception:
                        pass

        # General search with multiple query variants
        for qi, query in enumerate(query_variants):
            if len(search_urls) >= max_candidates:
                break
            if qi == 0:
                send("search_phase", {"index": idx, "phase": "general", "query": query})
            for sn, searcher in [("bing", bing_scraper), ("ddg", ddg), ("pexels", pexels)]:
                if sn == "pexels" and not pexels.available:
                    continue
                try:
                    sr = searcher.search(query, max_results=max_candidates)
                    if sr:
                        collect(sr, sn)
                        break
                except Exception:
                    pass
            if len(search_urls) >= max_candidates:
                break  # Have enough URLs to evaluate

        if not search_urls:
            send("product_done", {
                "index": idx, "product_id": product_id, "denumire": denumire,
                "status": "no_results", "images": [], "source": "none",
            })
            stats["failed"] += 1
            results.append({"id": product_id, "denumire": denumire,
                            "status": "failed", "images": []})
            continue

        source_used = search_urls[0][1] if search_urls else "none"

        # ── DOWNLOAD ALL IN PARALLEL ──
        all_urls = [u for u, _ in search_urls]
        url_to_source = {u: s for u, s in search_urls}
        downloaded = download_images_parallel(all_urls, max_workers=6)

        send("status", {"message": f"Downloaded {len(downloaded)}/{len(all_urls)} images"})

        # ── EVALUATE: quality + CLIP, collect valid candidates ──
        saved_images = []
        candidates_tried = 0
        valid_candidates = []  # [(data, qc, relevance_score, url, img_hash, src)]
        seen_hashes = set()

        for url, src in search_urls:
            data = downloaded.get(url)
            if not data:
                continue
            candidates_tried += 1

            # Quality check
            qc = quality_checker.evaluate(data)
            if not qc["passed"]:
                send("candidate_checked", {
                    "index": idx, "url": url[:100],
                    "quality_score": qc["score"], "passed": False,
                    "reasons": qc["reasons"], "details": qc["details"],
                    "relevance_score": None,
                })
                continue

            # Deduplicate
            img_hash = hashlib.md5(data).hexdigest()
            if img_hash in seen_hashes:
                continue
            seen_hashes.add(img_hash)

            # Relevance scoring: combine CLIP + URL keyword matching
            clip_score = 50
            url_score = url_keyword_score(url, denumire)
            url_score_100 = round(url_score * 100)

            if relevance_checker:
                rc = relevance_checker.check(data, denumire)
                clip_score = rc["score"]

                # Combined score: 70% CLIP + 30% URL keywords
                relevance_score = round(clip_score * 0.7 + url_score_100 * 0.3)

                if not rc["relevant"] and url_score < 0.5:
                    send("candidate_checked", {
                        "index": idx, "url": url[:100],
                        "quality_score": qc["score"], "passed": False,
                        "reasons": [rc["reason"]],
                        "details": {**qc["details"], "relevance": rc["similarity"],
                                    "url_match": url_score_100},
                        "relevance_score": relevance_score,
                    })
                    continue
            else:
                relevance_score = url_score_100

            send("candidate_checked", {
                "index": idx, "url": url[:100],
                "quality_score": qc["score"], "passed": True,
                "reasons": [],
                "details": {**qc["details"], "url_match": url_score_100,
                            "clip": clip_score},
                "relevance_score": relevance_score,
            })

            valid_candidates.append((data, qc, relevance_score, url, img_hash, src))

            # EARLY STOP: only if we have enough great matches for ALL requested images
            if len(valid_candidates) >= images_per_product:
                great_count = sum(1 for c in valid_candidates if c[2] >= GREAT_RELEVANCE)
                if great_count >= images_per_product:
                    break
                # Without CLIP: stop after enough candidates
                if not relevance_checker:
                    break

        # Sort by relevance (highest first) and save top N
        valid_candidates.sort(key=lambda c: c[2], reverse=True)

        for data, qc, rel_score, url, img_hash, src in valid_candidates[:images_per_product]:
            try:
                processed = resize_and_pad(data, target_size, quality=quality,
                                           remove_bg=remove_bg,
                                           output_format=output_format)
                img_num = len(saved_images) + 1
                filename = hermes_filename(product_id, denumire, img_num,
                                           fmt=output_format)
                filepath = output_dir / filename
                filepath.write_bytes(processed)

                thumb = make_thumbnail(processed)

                try:
                    image_domain = urlparse(url).netloc.replace("www.", "")
                except Exception:
                    image_domain = ""

                saved_images.append({
                    "filename": filename,
                    "quality_score": qc["score"],
                    "relevance_score": rel_score,
                    "source": src,
                    "image_url": url,
                    "image_domain": image_domain,
                    "hash": img_hash,
                    "thumbnail": thumb,
                    "details": qc["details"],
                })
            except Exception as e:
                logger.debug(f"Process error for {denumire}: {e}")

        status = "ok" if saved_images else "failed"
        if saved_images:
            stats["success"] += 1
            stats["images_saved"] += len(saved_images)
        else:
            stats["failed"] += 1

        send("product_done", {
            "index": idx, "product_id": product_id, "denumire": denumire,
            "status": status, "images": saved_images, "source": source_used,
            "candidates_tried": candidates_tried,
        })

        results.append({
            "id": product_id, "denumire": denumire,
            "status": status, "images": saved_images,
        })

        # Minimal delay to avoid rate limiting
        if idx < len(products) - 1:
            time.sleep(0.1)

    send("job_done", {
        "job_id": job_id,
        "stats": stats,
        "output_dir": str(output_dir.resolve()),
    })


# ─── FILE PARSERS ─────────────────────────────────────────────────────────

def parse_uploaded_file(file_storage) -> list[str]:
    """
    Extract product names from uploaded file.
    Supports: .xlsx, .xls, .csv, .tsv, .txt, .docx, .pdf
    Returns a list of product name strings.
    """
    filename = file_storage.filename.lower()
    data = file_storage.read()

    if filename.endswith((".xlsx", ".xls")):
        return _parse_excel(data)
    elif filename.endswith(".csv"):
        return _parse_csv(data, ",")
    elif filename.endswith(".tsv"):
        return _parse_csv(data, "\t")
    elif filename.endswith(".txt"):
        return _parse_txt(data)
    elif filename.endswith(".docx"):
        return _parse_docx(data)
    elif filename.endswith(".pdf"):
        return _parse_pdf(data)
    else:
        raise ValueError(f"Unsupported file type: {filename}")


def _parse_excel(data: bytes) -> list[str]:
    """Parse .xlsx - takes the first column with text data, or a 'denumire' column."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Check header row for a known column name
    header = [str(c).lower().strip() if c else "" for c in rows[0]]
    target_col = None
    for keyword in ["denumire", "produs", "product", "name", "nume", "descriere", "description", "item"]:
        if keyword in header:
            target_col = header.index(keyword)
            break

    if target_col is not None:
        # Use the identified column, skip header
        lines = [str(row[target_col]).strip() for row in rows[1:] if row[target_col]]
    else:
        # Auto-detect: use the first column that has mostly text
        # Try each column, pick the one with most non-empty string values
        best_col = 0
        best_count = 0
        num_cols = max(len(r) for r in rows) if rows else 0
        for ci in range(num_cols):
            count = sum(1 for r in rows if len(r) > ci and r[ci]
                        and isinstance(r[ci], str) and len(str(r[ci]).strip()) > 2)
            if count > best_count:
                best_count = count
                best_col = ci

        # Check if first row looks like a header
        first_val = str(rows[0][best_col]).strip() if rows[0][best_col] else ""
        start = 1 if (first_val.lower() in header or len(first_val) < 20) else 0
        lines = [str(row[best_col]).strip() for row in rows[start:]
                 if len(row) > best_col and row[best_col] and str(row[best_col]).strip()]

    wb.close()
    return [l for l in lines if l and l.lower() != "none"]


def _parse_csv(data: bytes, delimiter: str) -> list[str]:
    """Parse CSV/TSV - same logic as Excel: find 'denumire' column or first text column."""
    import csv as csv_mod
    text = data.decode("utf-8-sig", errors="replace")
    # Auto-detect delimiter if comma doesn't produce multiple columns
    reader = list(csv_mod.reader(io.StringIO(text), delimiter=delimiter))
    if not reader:
        return []

    # Also try semicolon (common in RO)
    if delimiter == "," and all(len(r) <= 1 for r in reader[:5]):
        reader = list(csv_mod.reader(io.StringIO(text), delimiter=";"))

    header = [str(c).lower().strip() for c in reader[0]] if reader else []
    target_col = None
    for keyword in ["denumire", "produs", "product", "name", "nume", "descriere", "description", "item"]:
        if keyword in header:
            target_col = header.index(keyword)
            break

    if target_col is not None:
        return [row[target_col].strip() for row in reader[1:] if len(row) > target_col and row[target_col].strip()]

    # Fallback: first column with longest average text
    if reader:
        num_cols = max(len(r) for r in reader)
        best_col = 0
        best_avg = 0
        for ci in range(num_cols):
            vals = [r[ci] for r in reader[1:] if len(r) > ci and r[ci].strip()]
            avg = sum(len(v) for v in vals) / max(len(vals), 1)
            if avg > best_avg:
                best_avg = avg
                best_col = ci
        return [row[best_col].strip() for row in reader[1:] if len(row) > best_col and row[best_col].strip()]

    return []


def _parse_txt(data: bytes) -> list[str]:
    """Parse plain text - one product per line."""
    text = data.decode("utf-8-sig", errors="replace")
    return [line.strip() for line in text.splitlines() if line.strip()]


def _parse_docx(data: bytes) -> list[str]:
    """Parse .docx - extract paragraphs and table cells."""
    from docx import Document
    doc = Document(io.BytesIO(data))
    lines = []

    # Paragraphs
    for para in doc.paragraphs:
        text = para.text.strip()
        if text and len(text) > 2:
            lines.append(text)

    # Tables (often product lists are in tables)
    for table in doc.tables:
        header = [cell.text.lower().strip() for cell in table.rows[0].cells] if table.rows else []
        target_col = None
        for keyword in ["denumire", "produs", "product", "name", "nume"]:
            if keyword in header:
                target_col = header.index(keyword)
                break

        start_row = 0
        if target_col is not None:
            start_row = 1
        else:
            # Use first column with longest text
            target_col = 0

        for row in table.rows[start_row:]:
            cells = row.cells
            if len(cells) > target_col:
                text = cells[target_col].text.strip()
                if text and len(text) > 2:
                    lines.append(text)

    return lines


def _parse_pdf(data: bytes) -> list[str]:
    """Parse .pdf - extract text lines."""
    import fitz  # pymupdf
    doc = fitz.open(stream=data, filetype="pdf")
    lines = []
    for page in doc:
        text = page.get_text()
        for line in text.splitlines():
            line = line.strip()
            if line and len(line) > 2:
                lines.append(line)
    doc.close()
    return lines


# ─── API ROUTES ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Upload a file and extract product names from it."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    try:
        products = parse_uploaded_file(f)
        return jsonify({
            "products": products,
            "count": len(products),
            "filename": f.filename,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"File parse error: {e}")
        return jsonify({"error": f"Failed to parse file: {str(e)}"}), 500


@app.route("/api/stop/<job_id>", methods=["POST"])
def stop_job(job_id):
    """Cancel a running job."""
    job = active_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job["status"] = "cancelled"
    return jsonify({"ok": True, "job_id": job_id})


@app.route("/api/start", methods=["POST"])
def start_job():
    """Start a scraping job. Expects JSON with products list and config."""
    payload = request.json
    products = payload.get("products", [])
    config = payload.get("config", {})

    if not products:
        return jsonify({"error": "No products provided"}), 400

    job_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    event_queue = queue.Queue()

    thread = threading.Thread(
        target=run_scraper_job,
        args=(job_id, products, config, event_queue),
        daemon=True,
    )

    active_jobs[job_id] = {
        "thread": thread,
        "queue": event_queue,
        "status": "running",
        "config": config,
    }

    thread.start()
    return jsonify({"job_id": job_id})


@app.route("/api/stream/<job_id>")
def stream_events(job_id):
    """SSE endpoint for real-time progress updates."""
    job = active_jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        while True:
            try:
                msg = job["queue"].get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("event") == "job_done":
                    job["status"] = "done"
                    break
            except queue.Empty:
                yield "data: {\"event\": \"heartbeat\"}\n\n"
                if not job["thread"].is_alive():
                    yield f'data: {json.dumps({"event": "job_done", "data": {"error": "Thread died"}})}\n\n'
                    break

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/api/images/<job_id>/<filename>")
def serve_image(job_id, filename):
    """Serve a downloaded image."""
    img_dir = OUTPUT_DIR / job_id
    return send_from_directory(str(img_dir), filename)


@app.route("/api/jobs")
def list_jobs():
    """List all jobs and their status."""
    return jsonify({
        jid: {"status": j["status"], "config": j["config"]}
        for jid, j in active_jobs.items()
    })


# ─── MAIN ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Image Scraper UI")
    parser.add_argument("--port", "-p", type=int, default=8787)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print(f"\n  Image Scraper UI running at http://localhost:{args.port}\n")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
