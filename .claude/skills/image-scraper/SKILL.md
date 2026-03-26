# Image Scraper - Project Context Skill

## Overview
Python Flask app (~3300 lines in `app.py`) for Hermes B2B. Scrapes product images from e-commerce sites.
Frontend: vanilla JS in `templates/index.html`. Single-file backend: `app.py`.

## Architecture Flow
```
User uploads product list → run_scraper_job() → for each product:
  1. PRIORITY SITES (direct scraping):
     build_direct_search_queries() → DirectSiteScraper.search() → collect images
  2. GENERAL SEARCH (Bing/DuckDuckGo/Pexels):
     build_search_variants() → BingImageScraper/DuckDuckGoSearch → collect images
  3. SCORING & FILTERING:
     For each image: quality check → relevance check (CLIP + URL keywords) → save best
```

## Key Classes & Functions (with line ranges — verify with grep)

### Product Matching
- **`AIProductMatcher`** (~L434-710): Matches product names to search result entries
  - `_PRODUCT_TYPES` dict: maps type keys to word sets (puree, syrup, tea, coffee, cream...)
  - `_detect_product_type(text)`: Context-aware type detection. "Blueberry Cream" → NOT type cream (v3.6+)
  - `_CREAM_FLAVOR_PREFIXES`: Words before "cream" that make it a flavor, not a product type
  - `_local_match()`: Synonym-aware scoring. Brand words +10, product words +6, type mismatch → hard skip
  - `match()`: Tries AI match first (if API key), then local. Post-filter removes type mismatches from AI output
  - `_tokenize()`: Splits text into normalized tokens. Has noise word set (mic, mare, mediu, mini, etc.)

### Direct Site Scraping
- **`DirectSiteScraper`** (~L715-1260): Scrapes specific e-commerce sites
  - `SEARCH_PATTERNS`: 9 URL patterns (Searchanise, Magento, Shopify, WooCommerce, CS-Cart, etc.)
  - `search(site, query, product_name)`: Main entry point. Flow:
    1. Try each SEARCH_PATTERN → extract product links → AI/local match → visit best page → extract images
    2. **Conflicting product check** on best_entries URLs and titles (v3.5+)
    3. **Rescue search**: If all top entries conflict, search ALL candidates for distinctive name words (v3.7+)
    4. Fallback: `_try_slug_url()` → `_try_brand_page()`
  - `_extract_product_entries(html, base_url)`: Parses `<a>` tags with product-like hrefs, extracts title/alt/context
  - `_extract_product_links(html, base_url, query)`: Calls _extract_product_entries + ranks by relevance
  - `_extract_product_images(product_url)`: Visits product page, extracts images via og:image → JSON-LD → gallery → Magento catalog → generic
  - `_try_slug_url(base_url, query)`: Constructs product URLs from slugified name. Type check + conflict check
  - `_try_brand_page(base_url, query)`: Crawls /brands/{brand} pages. AI match + type filter + conflict check

### Conflict Detection
- **`url_has_conflicting_product(url, product_name)`** (~L1931): Two-level check:
  1. **Flavor conflict**: URL has flavor words (mango, jasmine, green...) absent from product name variants
  2. **Product line mismatch**: Product has distinctive words (e.g. "paulista") missing from URL, while URL has different distinctive words (e.g. "crema", "gusto"). Excludes infrastructure words (media, cache, catalog, product, image, etc.)

### Query Building
- **`build_direct_search_queries(cleaned_name, key_words)`** (~L2285): Smart query variants:
  1. Brand + EN flavor (best for most sites)
  2. Brand + original flavor
  3. Just brand (broad)
  4. Concatenated brand (TeaTales)
  5. Brand + type + flavor
  6. Full cleaned name
  7. All-EN translation
  8. RO synonym variants
- **`clean_product_query(denumire)`** (~L2404): Strips noise (sizes, packaging, "NEW", "mic"/"mare")
- **`_NOISE_PATTERNS`** (~L1897): Regexes for packaging noise (4gr, 0.5L, 20plic/cut, etc.)

### Translation & Synonyms
- **`_RO_EN_MAP`** (~L1912): Romanian → English product word translations (ceai→tea, cafea→coffee, afine→blueberry...)
- **`get_word_variants(word)`**: Returns all known variants across languages (RO, EN, FR, DE, ES, IT)
- **`normalize_to_english(word)`**: Converts RO word to EN equivalent

### Scoring Flow (inside run_scraper_job ~L2531)
- Priority site images: `relevance_score = max(score, clip_score, 75)` — minimum 75, never rejected by CLIP alone
- Priority site conflict check uses **product_url** (not image URL) via `img_to_product_url` dict
- General search: rejected if CLIP < threshold AND url_keyword_score < 0.5, or if conflicting product detected
- `collect()` function stores `(image_url, source)` tuples + maps image→product_url in `img_to_product_url`

## Common Bug Patterns

### 1. Type Mismatch (Sirop vs Pireu)
`_detect_product_type` detects wrong type → matcher skips correct product.
**Fix pattern**: Check if the type word is contextual (e.g. "cream" after a flavor word = flavor, not type).

### 2. Wrong Product from Same Brand (Green Jasmine vs Blueberry Cream)
Search returns multiple products, matcher picks wrong one. CLIP can't distinguish similar packaging.
**Fix pattern**: `url_has_conflicting_product()` checks flavor/variant words + product line words.

### 3. Multiple Code Paths Bypass Filters
`search()` → `_try_slug_url()` → `_try_brand_page()` each produce results independently.
**Fix pattern**: Apply type filter AND conflict check in ALL three paths.

### 4. Priority Sites Skip Validation
Priority images get min score 75 and used to bypass ALL conflict checks.
**Fix pattern**: Apply `url_has_conflicting_product` on product_url even for priority images.

### 5. Noise Words Pollute Queries
Romanian words like "mic" (small), "mare" (large) create bad slug URLs.
**Fix pattern**: Add to ALL noise/filler word sets (there are 4+ separate sets in different functions).

### 6. Search Doesn't Find Product
Site search returns other products from same brand. Product exists but isn't in search results.
**Fix pattern**: "Rescue search" — when all matcher picks are rejected, search ALL candidates for distinctive name words.

## Debug Prints
All prefixed: `[SEARCH]`, `[MATCHER]`, `[LOCAL]`, `[BRAND]`, `[SLUG]`, `[FALLBACK]`, `[PRIORITY]`, `[PRIORITY-FILTER]`, `[CONFLICT]`

### 7. Category Pages Treated as Products
URLs like `/cafea/cafea-boabe/lavazza` pass `_is_product_url` but are listings, not products.
Images from category pages are random brand thumbnails.
**Fix pattern**: Priority filter checks if product_url is multi-segment category. Also pre-filter requires distinctive product words in entries.

### 8. Searchanise Cloud API Integration
Sites using Searchanise render search results via JS (useless with `requests.get`).
**Solution**: `_try_searchanise_api()` method (Phase 0 in `search()`):
1. Auto-discovers API key from page source (regex near `Searchanise` or `searchserverapi`)
2. Queries `{host}/getresults?api_key={key}&q={product_name}&maxResults=10`
3. Pre-filters results with distinctive product words, runs conflict check
4. Cache: `_searchanise_keys` dict (domain → key). Key format: 8+ alphanumeric chars.
**Known keys**: kfea.ro → `3G8U0J5H9f`, host `https://searchserverapi.com`

### 9. Known Site-Specific Issues
- **kfea.ro**: Uses Searchanise cloud API (Phase 0). Magento catalogsearch returns poor results for specific products like "LAVAZZA PAULISTA". Searchanise API finds it correctly.
- **beanzcafe.ro**: Magento search works well. Product URLs use slugs like `teatales-blueberry-cream-4g`.

## Key Config
- `priority_sites`: List of e-commerce domains to scrape directly first
- `search_suffix`: Appended to general search queries (default: "product photo")
- `max_candidates`: Max images to collect per product
- CLIP model: OpenCLIP ViT-B-32 for visual relevance checking
- No API key needed for local matching (AI matching optional with Anthropic key)
