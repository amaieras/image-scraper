# Image Scraper - Hermes B2B

## Cum se pornește

```bash
cd image-scraper
source venv/bin/activate
venv/bin/pip install -r requirements.txt
venv/bin/python app.py --port 8080
```

Deschide `http://localhost:8080` în browser.

---

## Funcționalități

### Input produse

- **Free Text** — lipești denumirile de produs, câte una pe linie
- **Import File** — drag & drop sau click to browse, formate acceptate:
  - `.xlsx` / `.xls` — detectează automat coloana cu denumiri (caută "denumire", "produs", "product", "name" etc.)
  - `.csv` / `.tsv` — auto-detect separator (virgulă, semicolon, tab)
  - `.txt` — un produs pe linie
  - `.docx` — extrage din paragrafe și tabele
  - `.pdf` — extrage text linie cu linie
- La import fișier, produsele sunt populate și în tab-ul Free Text pentru editare/review

### Căutare imagini

- **Priority Sites** — domenii unde se caută întâi (cu `site:domeniu.com`), fallback la căutare generală dacă nu găsește
- **Surse de căutare (în ordine)**:
  1. Bing Image Scrape (gratuit, fără API key)
  2. DuckDuckGo (gratuit, rate limited)
  3. Pexels API (necesită key, 200 req/oră, stock generic)
- **Search Suffix** — text adăugat automat la query (default: "product photo"). Pe priority sites se caută fără suffix pentru precizie maximă

### Controlul calității

- **Quality Score (0-100)** — scor compus din 5 factori:
  - Rezoluție sursă (30% din scor)
  - Aspect ratio (15%) — preferă imagini pătrate
  - Claritate/blur detection via edge detection (25%)
  - Diversitate culori (15%) — respinge placeholdere/imagini uniforme
  - Mărime fișier (15%)
- **Min Quality Score** — pragul minim pentru acceptare (default: 60)
- **Min Source Resolution** — rezoluția minimă a imaginii sursă (default: 600px)
- **Surse configurate pentru imagini mari** — Bing cere `imagesize-large`, DuckDuckGo cere `size=Large`
- **Reject Blurry** — activat permanent, respinge imaginile neclare
- **AI Relevance Check (CLIP)** — verifică dacă imaginea descărcată chiar corespunde produsului cerut. Folosește OpenCLIP (ViT-B-32) pentru a compara embedding-ul imaginii cu textul produsului. Include self-test la încărcare pentru a detecta erori. Modelul se încarcă o singură dată (lazy load) și rulează local.
- **URL Keyword Matching** — analizează URL-ul imaginii și verifică câte cuvinte din numele produsului apar în el. Dacă URL-ul conține "lavazza-gustoso-1kg", e semn foarte bun. Funcționează și fără CLIP.
- **Scor combinat** — relevanța finală e 70% CLIP + 30% URL keywords. Dacă CLIP nu e disponibil, se folosește doar URL matching.
- **Căutare multi-query** — încearcă variante: exact match cu ghilimele, cu suffix, simplificat. Prima variantă care returnează rezultate e folosită.
- **Deduplicare** — hash MD5, nu salvează aceeași imagine de două ori
- **Preseturi rapide**: Fast / Balanced / High Quality (default: High Quality)

### Procesare imagine

- **Output Size** — dimensiunea finală (default: 200×200px). Sursele sunt căutate la rezoluție mare (min 600px) și redimensionate la output, ceea ce păstrează claritatea
- **Format Ieșire** — WebP (default, recomandat pentru web, ~50% mai mic ca JPEG), JPEG (compatibilitate maximă), PNG (lossless). WebP și PNG suportă transparență cu Remove Background activ
- **Calitate Compresie** — 90 default, se aplică la WebP și JPEG (nu PNG)
- **Remove Background (AI)** — opțional, folosește rembg/U2Net pentru fundal alb pur
- **Padding și centrare** — imaginea e redimensionată păstrând proporțiile, centrată pe fundal alb
- **Convenție denumire Hermes**: `{ID_Produs}{comentariu}#N.jpg` (ex: `1}{cafealavazzapaulista1kgboabe}#1.jpg`)

### Configurare avansată

- **Images per Product** (1-5) — câte imagini distincte per produs (default: 2)
- **Max Candidates** (3-20) — câți candidați evaluează per produs (default: 15)
- **Min/Max Aspect Ratio** — filtrează imagini prea late sau prea înguste
- **API Keys** (opțional) — Pexels, Bing Image Search

### Performanță (optimizat pentru 10k+ produse)

- **Download paralel** — toate imaginile candidat pentru un produs se descarcă simultan (6 threads), nu secvențial. Reduce timpul per produs de la ~15s la ~5-7s
- **Smart search** — dacă priority sites au returnat suficiente rezultate, skip general search (economisește 1-2s per produs)
- **Early-stop** — dacă CLIP găsește un candidat cu relevanță >80, se oprește imediat fără să verifice restul
- **Fără CLIP** — ia primul candidat care trece quality check, zero overhead
- **Delay-uri minimale** — Bing 0.5s, între produse 0.1s, download timeout 8s
- **Stop Scraping** — buton de oprire care anulează job-ul curent, păstrând ce s-a descărcat deja
- **~7s per produs cu CLIP, ~3s fără** — ~20 produse/minut

### Progress și rezultate

- **Progress bar** cu procent în timp real
- **Statistici live**: Total / Processed / Success / Failed
- **Stop button** — oprește scraping-ul în curs
- **Log detaliat** per candidat — scor, motiv reject, sursă
- **Galerie rezultate** cu thumbnails, status, sursă, scor calitate
- **SSE (Server-Sent Events)** — streaming real-time din backend

---

## Deploy

### macOS
```bash
chmod +x deploy-osx.sh
./deploy-osx.sh
```

### Linux (Ubuntu/Debian/CentOS/Fedora/Arch)
```bash
chmod +x deploy-linux.sh
sudo ./deploy-linux.sh
```

### Windows
```
deploy-windows.bat
```
Sau double-click pe `deploy-windows.bat`.

Toate scripturile instalează totul de la zero dacă lipsește (inclusiv Python), verifică versiunile, creează venv, instalează dependențele (PyTorch, CLIP, numpy<2), și pre-descarcă modelul AI.

### Producție
```bash
# Linux/macOS (gunicorn)
pip install gunicorn
gunicorn -w 2 --threads 4 -b 0.0.0.0:8080 app:app

# Windows (waitress)
pip install waitress
waitress-serve --port=8080 app:app
```

## Structura fișiere

```
image-scraper/
├── app.py              # Flask backend + search engines + quality checker + file parsers
├── index.html          # Frontend HTML (layout only)
├── static/
│   ├── style.css       # All CSS styles
│   ├── state.js        # Shared global state and utilities
│   ├── ui.js           # Stats display, logging, lightbox, theme
│   ├── approval.js     # Image selection (radio behavior), approval workflow
│   ├── replace.js      # Replace image via URL download
│   ├── scraper.js      # Start/stop scraping, SSE events, result cards
│   └── app.js          # Config, presets, input handling, tabs, init
├── scraper.py          # CLI scraper original (standalone, fără UI)
├── deploy-osx.sh       # Deploy macOS (auto-install Homebrew + Python)
├── deploy-linux.sh     # Deploy Linux (auto-install Python, suport multi-distro)
├── deploy-windows.bat  # Deploy Windows (auto-download Python installer)
├── image-scraper.service # Systemd service file (Linux production)
├── requirements.txt    # Dependențe Python
├── produse.csv         # CSV exemplu cu produse
└── output/             # Imagini descărcate (organizate per job_id)
```

## Dependențe

- flask, requests, Pillow, numpy — core
- ddgs — DuckDuckGo search
- openpyxl — Excel parsing
- python-docx — Word parsing
- pymupdf — PDF parsing
- open-clip-torch, sentence-transformers — AI relevance verification (CLIP)
- rembg, onnxruntime — background removal (opțional)
- rich — CLI formatting (pentru scraper.py standalone)
