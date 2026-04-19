// ─── App: Presets, Config, Input, Tabs, Drag & Drop, Reset ─────────
// Depends on: state.js, ui.js, scraper.js, approval.js, replace.js
// This is the main entry point — loaded last.

// ─── Presets ────────────────────────────────────────────────────────

const presets = {
  fast:     { minQualityScore:20, minResolution:400, maxCandidates:5, imagesPerProduct:1, outputSize:200, quality:90 },
  balanced: { minQualityScore:40, minResolution:600, maxCandidates:10, imagesPerProduct:1, outputSize:200, quality:95 },
  quality:  { minQualityScore:60, minResolution:800, maxCandidates:15, imagesPerProduct:1, outputSize:200, quality:98 },
};

function applyPreset(name) {
  const p = presets[name];
  if (!p) return;
  document.getElementById('minQualityScore').value = p.minQualityScore;
  document.getElementById('qualityScoreVal').textContent = p.minQualityScore;
  document.getElementById('minResolution').value = p.minResolution;
  document.getElementById('useMinResolution').checked = true;
  toggleMinRes();
  document.getElementById('minResVal').textContent = p.minResolution;
  document.getElementById('maxCandidates').value = p.maxCandidates;
  document.getElementById('maxCandVal').textContent = p.maxCandidates;
  document.getElementById('imagesPerProduct').value = p.imagesPerProduct;
  document.getElementById('imagesPerVal').textContent = p.imagesPerProduct;
  if (p.outputSize) {
    document.getElementById('imageWidth').value = p.outputSize;
    document.getElementById('imageHeight').value = p.outputSize;
  }
  if (p.quality) {
    document.getElementById('quality').value = p.quality;
    document.getElementById('qualityVal').textContent = p.quality;
  }
  document.querySelectorAll('.chip').forEach(c =>
    c.classList.toggle('active', c.dataset.preset === name));
}

// ─── Min Resolution toggle ──────────────────────────────────────────

function toggleMinRes() {
  const cb = document.getElementById('useMinResolution');
  const slider = document.getElementById('minResolution');
  const valLabel = document.getElementById('minResVal');
  if (cb.checked) {
    slider.disabled = false;
    slider.style.opacity = '1';
    valLabel.style.opacity = '1';
    valLabel.textContent = slider.value;
  } else {
    slider.disabled = true;
    slider.style.opacity = '0.35';
    valLabel.style.opacity = '0.4';
    valLabel.textContent = 'off';
  }
}

// ─── Input helpers ──────────────────────────────────────────────────

const productInput = document.getElementById('productInput');
productInput.addEventListener('input', updateLineCount);

function updateLineCount() {
  const lines = productInput.value.trim().split('\n').filter(l => l.trim());
  document.getElementById('lineCount').textContent =
    `${lines.length} produs${lines.length !== 1 ? 'e' : ''}`;
  const hasContent = lines.length > 0 ||
    document.getElementById('progressSection').classList.contains('active');
  document.getElementById('resetBtn').disabled = !hasContent;
}

function clearInput() {
  productInput.value = '';
  fileProducts = [];
  fileHasIds = false;
  document.getElementById('fileBadge').style.display = 'none';
  document.getElementById('fileInput').value = '';
  updateLineCount();
}

// ─── Tabs ───────────────────────────────────────────────────────────

function switchTab(tab) {
  activeTab = tab;
  document.querySelectorAll('.input-tab').forEach(t =>
    t.classList.toggle('active', t.dataset.tab === tab));
  document.getElementById('tabText').style.display = tab === 'text' ? 'block' : 'none';
  document.getElementById('tabFile').style.display = tab === 'file' ? 'block' : 'none';
  updateLineCount();
}

// ─── Drag & Drop ────────────────────────────────────────────────────

const dropZone = document.getElementById('dropZone');

['dragenter', 'dragover'].forEach(evt =>
  dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.add('dragover'); }));
['dragleave', 'drop'].forEach(evt =>
  dropZone.addEventListener(evt, e => { e.preventDefault(); dropZone.classList.remove('dragover'); }));

dropZone.addEventListener('drop', e => {
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
});

async function handleFileSelect(file) {
  if (!file) return;

  const badge = document.getElementById('fileBadge');
  badge.innerHTML = `<span class="file-info">Se procesează <strong>${escapeHtml(file.name)}</strong>...</span>`;
  badge.style.display = 'flex';

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await resp.json();

    if (data.error) {
      badge.innerHTML = `
        <span class="file-info" style="color:var(--danger)">${escapeHtml(data.error)}</span>
        <button class="btn-remove" onclick="clearInput()" title="Elimină"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>`;
      return;
    }

    fileProducts = data.products;        // list of {id, denumire} dicts or strings
    fileHasIds = data.has_ids || false;   // whether Excel had id/cod column

    const idInfo = data.has_ids ? ' (cu ID-uri)' : '';
    badge.innerHTML = `
      <span class="file-info"><strong>${escapeHtml(file.name)}</strong> &mdash; ${data.count} produse${idInfo}</span>
      <button class="btn-remove" onclick="clearInput()" title="Elimină"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>`;

    // Display denumire lines in the textarea for visual reference
    const lines = data.products.map(p => typeof p === 'string' ? p : (p.denumire || ''));
    productInput.value = lines.join('\n');
    updateLineCount();
  } catch (err) {
    badge.innerHTML = `
      <span class="file-info" style="color:var(--danger)">Eroare: ${escapeHtml(err.message)}</span>
      <button class="btn-remove" onclick="clearInput()" title="Elimină"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>`;
  }
}

// ─── Priority Sites ─────────────────────────────────────────────────

function updateSiteCount() {
  const lines = document.getElementById('prioritySites').value.trim().split('\n').filter(l => l.trim());
  const el = document.getElementById('siteCount');
  el.textContent = lines.length > 0 ? `${lines.length} site-uri` : 'se caută întâi';
}

// ─── Config ─────────────────────────────────────────────────────────

function getConfig() {
  const sitesRaw = document.getElementById('prioritySites').value.trim();
  const prioritySites = sitesRaw ? sitesRaw.split('\n').map(s => s.trim()).filter(Boolean) : [];

  return {
    min_quality_score:  +document.getElementById('minQualityScore').value,
    min_resolution:     document.getElementById('useMinResolution').checked
                          ? +document.getElementById('minResolution').value
                          : 1,
    image_width:        +document.getElementById('imageWidth').value,
    image_height:       +document.getElementById('imageHeight').value,
    images_per_product: +document.getElementById('imagesPerProduct').value,
    output_format:      document.getElementById('outputFormat').value,
    quality:            +document.getElementById('quality').value,
    search_suffix:      document.getElementById('searchSuffix').value,
    max_candidates:     +document.getElementById('maxCandidates').value,
    check_relevance:    true,
    remove_background:  document.getElementById('removeBg').checked,
    reject_blurry:      true,
    pexels_key:         document.getElementById('pexelsKey').value,
    bing_key:           document.getElementById('bingKey').value,
    anthropic_key:      '',
    gemini_key:         document.getElementById('geminiKey').value,
    min_aspect_ratio:   +document.getElementById('minAspectRatio').value,
    max_aspect_ratio:   +document.getElementById('maxAspectRatio').value,
    priority_sites:     prioritySites,
    hermes_enabled:     document.getElementById('hermesEnabled')?.checked || false,
    hermes_output_path: document.getElementById('hermesOutputPath')?.value?.trim() || '',
    folder_name:        document.getElementById('folderName')?.value?.trim() || '',
  };
}

// ─── Toggle advanced ────────────────────────────────────────────────

function toggleAdvanced(el) {
  el.classList.toggle('open');
  document.getElementById('advancedSection').classList.toggle('open');
}

// ─── Reset All ──────────────────────────────────────────────────────

function resetAll() {
  clearInput();
  document.getElementById('prioritySites').value = '';
  updateSiteCount();
  applyPreset('quality');
  document.getElementById('useMinResolution').checked = false;
  toggleMinRes();
  document.getElementById('searchSuffix').value = 'product photo';
  document.getElementById('outputFormat').value = 'jpeg';
  document.getElementById('quality').value = 98;
  document.getElementById('qualityVal').textContent = '98';
  document.getElementById('qualityGroup').style.display = 'block';
  document.getElementById('removeBg').checked = false;
  document.getElementById('pexelsKey').value = '';
  document.getElementById('bingKey').value = '';
  const folderInput = document.getElementById('folderName');
  if (folderInput) folderInput.value = '';
  document.getElementById('minAspectRatio').value = 0.4;
  document.getElementById('minAspectVal').textContent = '0.4';
  document.getElementById('maxAspectRatio').value = 2.5;
  document.getElementById('maxAspectVal').textContent = '2.5';
  document.getElementById('progressSection').classList.remove('active');
  document.getElementById('resultsSection').classList.remove('active');
  document.getElementById('resultsGrid').innerHTML = '';
  document.getElementById('logContainer').innerHTML = '';
  document.getElementById('timerDisplay').textContent = '00:00';
  timerStart = null;
  pendingImages = {};
  approvalDone = false;
  hideApprovalToolbar();
  switchTab('text');
  document.getElementById('resetBtn').disabled = true;
}

// ─── Init ───────────────────────────────────────────────────────────
updateLineCount();
