#!/usr/bin/env python3
"""
Image Scraper pentru Hermes B2B
================================
Caută imagini de produs pe internet, le descarcă, le redimensionează
la 200x200 și le denumește conform convenției Hermes.

Surse (în ordine de prioritate):
  1. Pexels API (200 req/oră, gratuit, stabil)
  2. DuckDuckGo (fallback, fără API key, dar rate limited)

Convenție denumire: {ID_Produs}{Comentariu}#N.jpg
  Exemplu: 475}{alexandrion0.75l}#1.jpg

Utilizare:
    python scraper.py                              # Procesează produse.csv
    python scraper.py --fisier produse.csv
    python scraper.py --test                       # Test rapid 3 produse
    python scraper.py --id-field cod               # Folosește codul în loc de ID
    python scraper.py --pexels-key YOUR_KEY        # Pexels API key
    python scraper.py --resume                     # Continuă de unde a rămas
    python scraper.py --workers 4                  # Download-uri paralele
"""

import argparse
import csv
import io
import json
import re
import sys
import time
import hashlib
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps
from rich.console import Console
from rich.table import Table
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TaskProgressColumn, TimeRemainingColumn, MofNCompleteColumn,
)

console = Console()
logger = logging.getLogger("scraper")

# ─── CONFIG ──────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("./output")
IMAGE_SIZE = (200, 200)
BACKGROUND_COLOR = (255, 255, 255)
JPEG_QUALITY = 90
REQUEST_TIMEOUT = 15
PEXELS_DELAY = 0.5            # Pexels: 200 req/hr → safe la 0.5s
DDG_DELAY = 4                  # DuckDuckGo: agresiv cu rate limit
MAX_RETRIES = 3
DOWNLOAD_WORKERS = 4           # Threads paralele pentru download

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ─── DATABASE (RESUME) ──────────────────────────────────────────────────

class ProgressDB:
    """SQLite database for tracking progress and enabling resume."""

    def __init__(self, db_path: Path):
        self.db = sqlite3.connect(str(db_path))
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS processed (
                product_id TEXT PRIMARY KEY,
                denumire TEXT,
                images_saved INTEGER DEFAULT 0,
                source TEXT,
                status TEXT DEFAULT 'ok',
                processed_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.db.commit()

    def is_done(self, product_id: str) -> bool:
        cur = self.db.execute(
            "SELECT 1 FROM processed WHERE product_id = ? AND status = 'ok' AND images_saved > 0",
            (product_id,)
        )
        return cur.fetchone() is not None

    def record(self, product_id: str, denumire: str, images_saved: int,
               source: str, status: str = "ok"):
        self.db.execute("""
            INSERT OR REPLACE INTO processed (product_id, denumire, images_saved, source, status, processed_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (product_id, denumire, images_saved, source, status, datetime.now().isoformat()))
        self.db.commit()

    def stats(self) -> dict:
        cur = self.db.execute("SELECT COUNT(*), SUM(images_saved) FROM processed WHERE status='ok'")
        row = cur.fetchone()
        return {"products_done": row[0] or 0, "images_total": row[1] or 0}

    def failed_products(self) -> list[str]:
        cur = self.db.execute("SELECT product_id FROM processed WHERE status != 'ok' OR images_saved = 0")
        return [r[0] for r in cur.fetchall()]

    def close(self):
        self.db.close()


# ─── SEARCH: PEXELS ─────────────────────────────────────────────────────

class PexelsSearch:
    """Pexels API - 200 requests/hour, free."""

    BASE_URL = "https://api.pexels.com/v1/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Authorization"] = api_key
        self.request_count = 0
        self.hour_start = time.time()

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search Pexels. Returns list of {url, title, source}."""
        if not self.api_key:
            return []

        self._rate_limit_check()

        try:
            resp = self.session.get(
                self.BASE_URL,
                params={"query": query, "per_page": min(max_results, 15), "orientation": "square"},
                timeout=REQUEST_TIMEOUT,
            )
            self.request_count += 1

            if resp.status_code == 429:
                console.print("    [yellow]Pexels rate limit, aștept 60s...[/yellow]")
                time.sleep(60)
                return self.search(query, max_results)

            resp.raise_for_status()
            data = resp.json()

            results = []
            for photo in data.get("photos", []):
                src = photo.get("src", {})
                # 'medium' = 350px, 'large' = 940px, 'original' = full
                img_url = src.get("medium") or src.get("large") or src.get("original", "")
                if img_url:
                    results.append({
                        "image": img_url,
                        "title": photo.get("alt", ""),
                        "source": "pexels",
                        "photographer": photo.get("photographer", ""),
                    })
            return results

        except Exception as e:
            logger.debug(f"Pexels search error: {e}")
            return []

    def _rate_limit_check(self):
        """Ensure we don't exceed 200 req/hour."""
        elapsed = time.time() - self.hour_start
        if elapsed > 3600:
            self.request_count = 0
            self.hour_start = time.time()
        elif self.request_count >= 190:  # Leave 10 as buffer
            wait = 3600 - elapsed + 5
            console.print(f"    [yellow]Pexels hourly limit approaching, pauză {wait:.0f}s...[/yellow]")
            time.sleep(wait)
            self.request_count = 0
            self.hour_start = time.time()

    @property
    def available(self) -> bool:
        return bool(self.api_key)


# ─── SEARCH: BING SCRAPER (no API key) ───────────────────────────────────

class BingImageScraper:
    """
    Scrape Bing Images direct din HTML - fără API key.
    Găsește produse EXACTE (ex: Alexandrion, Jidvei etc).
    """

    SEARCH_URL = "https://www.bing.com/images/search"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9,ro;q=0.8",
        })
        self._last_call = 0

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        # Min delay between requests
        elapsed = time.time() - self._last_call
        if elapsed < 1.5:
            time.sleep(1.5 - elapsed)

        try:
            resp = self.session.get(
                self.SEARCH_URL,
                params={"q": query, "form": "HDRSC2", "first": "1"},
                timeout=REQUEST_TIMEOUT,
            )
            self._last_call = time.time()
            resp.raise_for_status()
        except Exception as e:
            logger.debug(f"Bing scrape error: {e}")
            return []

        # Extract image URLs from the page
        results = []
        # Bing embeds image data in 'murl' parameter within anchor tags
        import re as _re
        # Pattern: murl&quot;:&quot;URL&quot;
        urls = _re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)

        for url in urls[:max_results * 2]:  # Get extra, some may fail
            if len(results) >= max_results:
                break
            # Skip tiny/icon URLs
            if any(skip in url.lower() for skip in ['favicon', 'logo', '1x1', 'pixel', '.svg', '.gif']):
                continue
            results.append({
                "image": url,
                "title": query,
                "source": "bing_scrape",
            })

        return results


# ─── SEARCH: DUCKDUCKGO ─────────────────────────────────────────────────

class DuckDuckGoSearch:
    """DuckDuckGo image search - free, no API key, but aggressive rate limiting."""

    def __init__(self):
        self._last_call = 0

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        elapsed = time.time() - self._last_call
        if elapsed < DDG_DELAY:
            time.sleep(DDG_DELAY - elapsed)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.images(
                        keywords=query,
                        region="wt-wt",
                        safesearch="moderate",
                        size="Medium",
                        type_image="photo",
                        max_results=max_results,
                    ))
                self._last_call = time.time()
                for r in results:
                    r["source"] = "ddg"
                return results
            except Exception as e:
                if "Ratelimit" in str(e) or "403" in str(e):
                    wait = DDG_DELAY * attempt * 2
                    if attempt < MAX_RETRIES:
                        time.sleep(wait)
                        continue
                logger.debug(f"DDG search error: {e}")
                return []
        return []


# ─── SEARCH: BING ────────────────────────────────────────────────────────

class BingImageSearch:
    """Bing Image Search API - 1000 transactions/month free tier."""

    BASE_URL = "https://api.bing.microsoft.com/v7.0/images/search"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["Ocp-Apim-Subscription-Key"] = api_key

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        if not self.api_key:
            return []
        try:
            resp = self.session.get(
                self.BASE_URL,
                params={
                    "q": query,
                    "count": min(max_results, 15),
                    "imageType": "Photo",
                    "size": "Medium",
                },
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 401:
                logger.debug("Bing API key invalid")
                return []
            resp.raise_for_status()
            data = resp.json()

            results = []
            for img in data.get("value", []):
                url = img.get("contentUrl", "")
                if url:
                    results.append({
                        "image": url,
                        "title": img.get("name", ""),
                        "source": "bing",
                    })
            return results
        except Exception as e:
            logger.debug(f"Bing search error: {e}")
            return []

    @property
    def available(self) -> bool:
        return bool(self.api_key)


# ─── MULTI-SOURCE SEARCH ────────────────────────────────────────────────

class ImageSearcher:
    """
    Orchestrează căutarea pe multiple surse.
    Prioritate:
      1. Bing Scraper (gratis, fără API, produse EXACTE, ~1.5s/req)
      2. DuckDuckGo (gratis, produse exacte, dar rate limited agresiv)
      3. Bing API (1000/lună gratis, produse exacte)
      4. Pexels (200/oră gratis, stabil, dar stock generic - last resort)
    """

    def __init__(self, pexels_key: str = "", bing_key: str = ""):
        self.bing_scraper = BingImageScraper()
        self.ddg = DuckDuckGoSearch()
        self.bing_api = BingImageSearch(bing_key)
        self.pexels = PexelsSearch(pexels_key)
        self.stats = {"bing_scrape": 0, "ddg": 0, "bing_api": 0, "pexels": 0, "failed": 0}

    def search(self, query: str, max_results: int = 5) -> tuple[list[dict], str]:
        """
        Caută imagini. Returnează (results, source_used).
        """
        # 1. Bing Scraper - best for exact products, no API key needed
        results = self.bing_scraper.search(query, max_results)
        if results:
            self.stats["bing_scrape"] += 1
            return results, "bing"

        # 2. DuckDuckGo fallback
        results = self.ddg.search(query, max_results)
        if results:
            self.stats["ddg"] += 1
            return results, "ddg"

        # 3. Bing API (if key provided)
        if self.bing_api.available:
            results = self.bing_api.search(query, max_results)
            if results:
                self.stats["bing_api"] += 1
                return results, "bing_api"

        # 4. Pexels last resort (stock generic)
        if self.pexels.available:
            results = self.pexels.search(query, max_results)
            if results:
                self.stats["pexels"] += 1
                return results, "pexels"

        self.stats["failed"] += 1
        return [], "none"


# ─── DOWNLOAD & PROCESS ─────────────────────────────────────────────────

def download_image(url: str) -> bytes | None:
    """Descarcă o imagine și returnează bytes, sau None dacă eșuează."""
    try:
        resp = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            return None

        data = resp.content
        if len(data) < 2000:
            return None

        return data
    except Exception:
        return None


def download_first_valid(urls: list[str], num_needed: int = 1) -> list[bytes]:
    """Download imagini în paralel, returnează primele num_needed valide."""
    valid = []

    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(download_image, url): url for url in urls}
        for future in as_completed(futures):
            if len(valid) >= num_needed:
                break
            data = future.result()
            if data and is_valid_image(data):
                valid.append(data)

    return valid


def is_valid_image(data: bytes, min_size: int = 100) -> bool:
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        w, h = img.size
        return w >= min_size and h >= min_size
    except Exception:
        return False


def remove_background(data: bytes) -> bytes:
    """Elimină fundalul imaginii folosind AI (rembg/U2Net). Returnează PNG cu transparență."""
    from rembg import remove
    return remove(data)


def resize_and_pad(data: bytes, target_size: tuple[int, int] = IMAGE_SIZE) -> bytes:
    """
    Pipeline imagine:
    1. Elimină fundalul (AI) → transparență
    2. Pune pe fundal alb
    3. Redimensionează la target_size cu centrare
    """
    # Step 1: Background removal
    try:
        nobg = remove_background(data)
        img = Image.open(io.BytesIO(nobg)).convert("RGBA")
    except Exception:
        # Fallback: fără background removal
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGBA",):
            img = img.convert("RGBA")

    img = ImageOps.exif_transpose(img)

    # Step 2: Resize păstrând aspect ratio
    target_w, target_h = target_size
    img.thumbnail((target_w, target_h), Image.LANCZOS)

    # Step 3: Paste pe fundal alb, centrat
    result = Image.new("RGB", target_size, BACKGROUND_COLOR)
    paste_x = (target_w - img.size[0]) // 2
    paste_y = (target_h - img.size[1]) // 2
    result.paste(img, (paste_x, paste_y), mask=img.split()[3])

    buf = io.BytesIO()
    result.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


# ─── NAMING ──────────────────────────────────────────────────────────────

def sanitize_comment(denumire: str) -> str:
    """Transformă denumirea în comentariu valid pt filename."""
    s = denumire.lower().strip()
    s = (s.replace(' ', '').replace('ă', 'a').replace('â', 'a')
          .replace('î', 'i').replace('ș', 's').replace('ş', 's')
          .replace('ț', 't').replace('ţ', 't'))
    s = re.sub(r'[^a-z0-9._-]', '', s)
    return s


def hermes_filename(product_id: str, denumire: str, image_number: int) -> str:
    """
    Numele fișierului conform convenției Hermes.
    Exemplu: 475}{alexandrion0.75l}#1.jpg
    """
    comment = sanitize_comment(denumire)
    return str(product_id) + "}{" + comment + "}#" + str(image_number) + ".jpg"


# ─── PIPELINE ────────────────────────────────────────────────────────────

def process_product(product_id: str, denumire: str, num_images: int,
                    output_dir: Path, searcher: ImageSearcher) -> dict:
    """Pipeline complet pentru un produs."""
    result = {"id": product_id, "denumire": denumire, "saved": 0, "source": "none", "errors": []}

    query = f"{denumire} product photo"

    search_results, source = searcher.search(query, max_results=num_images * 3)
    result["source"] = source

    if not search_results:
        result["errors"].append("Nicio imagine găsită")
        return result

    # Collect URLs
    urls = [sr.get("image", "") for sr in search_results if sr.get("image")]
    if not urls:
        result["errors"].append("Nicio imagine validă în rezultate")
        return result

    # Download in parallel
    images = download_first_valid(urls, num_needed=num_images)

    # Deduplicate
    seen = set()
    unique_images = []
    for data in images:
        h = hashlib.md5(data).hexdigest()
        if h not in seen:
            seen.add(h)
            unique_images.append(data)

    # Resize and save
    saved = 0
    for data in unique_images:
        if saved >= num_images:
            break
        try:
            processed = resize_and_pad(data)
            saved += 1
            filename = hermes_filename(product_id, denumire, saved)
            (output_dir / filename).write_bytes(processed)
        except Exception as e:
            logger.debug(f"Process error: {e}")

    result["saved"] = saved
    if saved == 0:
        result["errors"].append("Nu s-a putut descărca nicio imagine validă")
    elif saved < num_images:
        result["errors"].append(f"Doar {saved}/{num_images} imagini")

    return result


# ─── CSV LOADING ─────────────────────────────────────────────────────────

def load_products(csv_path: str, id_field: str = "id") -> list[dict]:
    """Încarcă lista de produse din CSV. Separator: ;"""
    products = []
    path = Path(csv_path)
    if not path.exists():
        console.print(f"[red]Fișierul {csv_path} nu există![/red]")
        sys.exit(1)

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            products.append({
                "product_id": row.get(id_field, row.get("id", "")),
                "denumire": row.get("denumire", ""),
                "num_images": int(row.get("imagini_dorite", 1)),
            })
    return products


# ─── MAIN ────────────────────────────────────────────────────────────────

def run(csv_path: str, id_field: str = "id", pexels_key: str = "",
        bing_key: str = "", resume: bool = True):
    """Rulează scraper-ul pe toate produsele din CSV."""
    console.rule("[bold blue]Image Scraper - Hermes B2B")

    products = load_products(csv_path, id_field)
    console.print(f"\nProduse în fișier: [bold]{len(products)}[/bold]")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    db = ProgressDB(OUTPUT_DIR / "progress.db")

    # Skip already processed
    if resume:
        before = len(products)
        products = [p for p in products if not db.is_done(p["product_id"])]
        skipped = before - len(products)
        if skipped:
            console.print(f"Deja procesate (skip): [dim]{skipped}[/dim]")

    console.print(f"De procesat: [bold green]{len(products)}[/bold green]")

    if not products:
        console.print("[green]Toate produsele sunt deja procesate![/green]")
        _print_final_stats(db)
        db.close()
        return

    # Show available sources
    sources = ["DuckDuckGo (free)"]
    if bing_key:
        sources.append("Bing Images (1000/lună)")
    if pexels_key:
        sources.append("Pexels (200/oră, fallback)")
    console.print(f"Surse active: [bold]{' → '.join(sources)}[/bold]")

    # Estimate: DDG ~6s/product, Bing ~2s, Pexels ~2s
    avg_delay = 2 if bing_key else (3 if pexels_key else 6)
    est = timedelta(seconds=len(products) * avg_delay)
    console.print(f"Timp estimat: [bold]{_format_duration(est)}[/bold]")
    console.print(f"Director: [bold]{OUTPUT_DIR.resolve()}[/bold]\n")

    searcher = ImageSearcher(pexels_key, bing_key)
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("Procesare produse", total=len(products))

        for i, prod in enumerate(products):
            progress.update(task, description=f"[cyan]{prod['denumire'][:35]}[/cyan]")

            result = process_product(
                product_id=prod["product_id"],
                denumire=prod["denumire"],
                num_images=prod["num_images"],
                output_dir=OUTPUT_DIR,
                searcher=searcher,
            )

            status = "ok" if result["saved"] > 0 else "failed"
            db.record(prod["product_id"], prod["denumire"],
                      result["saved"], result["source"], status)

            progress.advance(task)

            # Minimal delay (DDG needs more, APIs need less)
            if i < len(products) - 1:
                time.sleep(0.3)

    # Final report
    elapsed = time.time() - start_time
    console.print(f"\n[bold]Timp total:[/bold] {_format_duration(timedelta(seconds=elapsed))}")
    s = searcher.stats
    console.print(f"[bold]Surse folosite:[/bold] Bing={s['bing_scrape']}, "
                  f"DDG={s['ddg']}, BingAPI={s['bing_api']}, "
                  f"Pexels={s['pexels']}, Eșuate={s['failed']}")
    _print_final_stats(db)

    # Export failed list
    failed = db.failed_products()
    if failed:
        failed_path = OUTPUT_DIR / "failed_products.txt"
        failed_path.write_text("\n".join(failed), encoding="utf-8")
        console.print(f"\n[yellow]Produse eșuate ({len(failed)}) salvate în: {failed_path}[/yellow]")

    db.close()
    console.rule("[bold green]Done!")


def run_test(pexels_key: str = "", bing_key: str = ""):
    """Test rapid cu 3 produse diverse."""
    console.rule("[bold blue]TEST MODE")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    searcher = ImageSearcher(pexels_key, bing_key)
    test_products = [
        ("475", "Alexandrion 5* 0.75L", 2),
        ("892", "Coca-Cola 0.33L doza", 1),
        ("1501", "Heineken 0.5L sticla", 1),
    ]

    for pid, name, num in test_products:
        console.print(f"\n[bold]{name}[/bold]")
        result = process_product(pid, name, num, OUTPUT_DIR, searcher)
        if result["saved"]:
            console.print(f"  [green]✓ {result['saved']} imagini ({result['source']})[/green]")
        else:
            console.print(f"  [red]✗ {result['errors']}[/red]")
        time.sleep(1)

    files = sorted(OUTPUT_DIR.glob("*.jpg"))
    console.print(f"\n[bold]Total fișiere:[/bold] {len(files)}")
    for f in files:
        console.print(f"  {f.name}")

    s = searcher.stats
    console.print(f"\n[bold]Surse:[/bold] Bing={s['bing_scrape']}, DDG={s['ddg']}, "
                  f"BingAPI={s['bing_api']}, Pexels={s['pexels']}")
    console.rule("[bold green]Test complet!")


def _print_final_stats(db: ProgressDB):
    stats = db.stats()
    table = Table(title="Statistici totale")
    table.add_column("Metric", style="bold")
    table.add_column("Valoare", justify="right")
    table.add_row("Produse procesate", str(stats["products_done"]))
    table.add_row("Imagini totale", str(stats["images_total"]))
    console.print(table)


def _format_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def main():
    parser = argparse.ArgumentParser(
        description="Image Scraper pentru Hermes B2B",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--fisier", "-f", default="produse.csv",
                        help="Fișier CSV cu produse (default: produse.csv)")
    parser.add_argument("--id-field", default="id", choices=["id", "cod"],
                        help="Câmpul folosit ca identificator")
    parser.add_argument("--output", "-o", default="./output",
                        help="Director de ieșire")
    parser.add_argument("--pexels-key", "-p", default="",
                        help="Pexels API key (gratuit de pe pexels.com/api)")
    parser.add_argument("--bing-key", "-b", default="",
                        help="Bing Image Search API key (1000/lună gratuit)")
    parser.add_argument("--test", "-t", action="store_true",
                        help="Test rapid cu 3 produse")
    parser.add_argument("--no-resume", action="store_true",
                        help="Procesează totul de la zero (nu skip deja procesate)")
    parser.add_argument("--size", default="200x200",
                        help="Dimensiune imagine (default: 200x200)")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Re-încearcă doar produsele eșuate")

    args = parser.parse_args()

    global OUTPUT_DIR, IMAGE_SIZE
    OUTPUT_DIR = Path(args.output)

    if "x" in args.size:
        w, h = args.size.split("x")
        IMAGE_SIZE = (int(w), int(h))

    # Also check env variables for API keys
    import os
    pexels_key = args.pexels_key or os.environ.get("PEXELS_API_KEY", "")
    bing_key = args.bing_key or os.environ.get("BING_API_KEY", "")

    if args.test:
        run_test(pexels_key, bing_key)
    else:
        run(args.fisier, args.id_field, pexels_key, bing_key, resume=not args.no_resume)


if __name__ == "__main__":
    main()
