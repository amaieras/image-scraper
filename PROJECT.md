# Image Scraper — Project Overview

A web-based tool for automated product image acquisition and curation, built for B2B e-commerce (Hermes platform). It searches multiple image sources, applies quality checks and AI verification, then lets users approve and export production-ready images.

## How It Works (End-to-End)

1. **Input** — User pastes product names or uploads a file (Excel, CSV, Word, PDF, plain text). Product IDs are preserved for Hermes naming.
2. **Search** — For each product, the system queries multiple sources in a fallback cascade: Bing scraper → DuckDuckGo → Bing API → Pexels API. Priority domains can be searched first.
3. **Quality filtering** — Each candidate image is scored 0–100 on resolution, aspect ratio, sharpness, color diversity, and file size. Blurry, tiny, or multi-product images are rejected.
4. **AI verification** (optional) — OpenCLIP checks relevance to the product description, detects wrong product types, and flags multi-item photos. Google Gemini reads packaging text via OCR. Claude Haiku matches products on e-commerce sites.
5. **Approval UI** — Results appear in a thumbnail gallery. Users select one image per product (radio-style), can replace or re-search, then approve.
6. **Export** — Approved images are saved in the chosen format. If Hermes mode is on, 800×800 JPEG copies are created with standardized naming (`{ID}{comment}#1.jpg`) and optionally copied to a network path.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask (Python 3.10+), SSE for real-time streaming |
| Frontend | Vanilla JS (6 modular files), CSS with dark/light themes |
| Image processing | Pillow, optional rembg for background removal |
| AI / ML | OpenCLIP ViT-B-32 (local), Google Gemini Flash (cloud), Claude Haiku (cloud) |
| Search engines | Bing scraper, DuckDuckGo (ddgs), Bing Image API, Pexels API |
| File parsing | openpyxl (Excel), python-docx (Word), PyMuPDF (PDF), csv |
| Database | SQLite (resume capability) |
| Deployment | Docker, systemd, Windows Service (NSSM), deploy scripts per OS |

## Key Features

- **Multi-source search** with automatic fallback (no API key required for basic use)
- **Composite quality scoring** — resolution, sharpness, aspect ratio, color diversity, file size
- **AI pipeline** — CLIP relevance + type checking, Gemini OCR, Claude product matching
- **Multi-product detection** — heuristic (aspect ratio, column analysis) + CLIP verification
- **Real-time progress** via SSE — live metrics, ETA, per-image scoring details
- **Approval workflow** — pending → approve → export, with per-image replace/re-search
- **Hermes B2B export** — standardized naming, 800×800 JPEG, local + network path output
- **3 quality presets** — Fast (speed), Balanced, Quality (precision)
- **Resume capability** — SQLite tracks progress, can restart interrupted jobs
- **File import** — Excel, CSV, Word, PDF, plain text with auto-detection of product columns
- **ZIP download** of all images per job

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET | Serve the single-page app |
| `/api/config` | GET/POST | Load/save configuration |
| `/api/upload` | POST | Parse uploaded file → product list |
| `/api/start` | POST | Start a scraping job |
| `/api/stream/{job_id}` | GET | SSE stream for real-time progress |
| `/api/stop/{job_id}` | POST | Cancel a running job |
| `/api/images/{job_id}/{filename}` | GET | Serve an image |
| `/api/download-zip/{job_id}` | GET | Download all images as ZIP |
| `/api/approve` | POST | Approve selections, create Hermes copies |
| `/api/replace` | POST | Download replacement image or search a site |

## Project Structure

```
image-scraper/
├── app.py                  # Flask backend (~5800 lines)
├── scraper.py              # Standalone CLI scraper
├── index.html              # Single-page app
├── config.json             # API keys (Gemini, etc.)
├── requirements.txt        # Python dependencies
├── Dockerfile              # Container build
├── render.yaml             # Render.com deployment config
├── static/
│   ├── style.css           # Responsive layout, dark/light themes
│   ├── state.js            # Global state & utilities
│   ├── ui.js               # Stats, logging, theme, lightbox
│   ├── scraper.js          # Start/stop, SSE, result cards
│   ├── approval.js         # Image selection & approval
│   ├── replace.js          # Image replacement workflow
│   └── app.js              # Config, presets, file upload, tabs
├── deploy-windows.bat      # Windows installer (auto-installs Python)
├── deploy-linux.sh         # Linux installer
├── deploy-osx.sh           # macOS installer
├── output/                 # Job output directories
│   └── {job_id}/
│       ├── _pending/       # Unapproved images
│       └── _hermes/        # Hermes-ready JPEG copies
└── input products/         # Sample input files
```

## Performance

- ~6–10s per product with CLIP, ~3–5s without
- ~20 products/min (CLIP on), ~40/min (CLIP off)
- 6 parallel download threads per product
- Handles 10,000+ products with resume
