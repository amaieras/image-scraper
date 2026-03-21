// ─── State ──────────────────────────────────────────────────────────
let currentJobId = null;
let eventSource = null;
let stats = { total: 0, done: 0, success: 0, failed: 0, images: 0 };
let activeTab = 'text';
let fileProducts = [];
let timerInterval = null;
let timerStart = null;

// ─── Presets ────────────────────────────────────────────────────────
const presets = {
  fast:     { minQualityScore:20, minResolution:200, maxCandidates:5, imagesPerProduct:1, outputSize:200 },
  balanced: { minQualityScore:40, minResolution:400, maxCandidates:10, imagesPerProduct:1, outputSize:200 },
  quality:  { minQualityScore:60, minResolution:600, maxCandidates:15, imagesPerProduct:1, outputSize:200 },
};

function applyPreset(name) {
  const p = presets[name];
  if (!p) return;
  document.getElementById('minQualityScore').value = p.minQualityScore;
  document.getElementById('qualityScoreVal').textContent = p.minQualityScore;
  document.getElementById('minResolution').value = p.minResolution;
  document.getElementById('minResVal').textContent = p.minResolution;
  document.getElementById('maxCandidates').value = p.maxCandidates;
  document.getElementById('maxCandVal').textContent = p.maxCandidates;
  document.getElementById('imagesPerProduct').value = p.imagesPerProduct;
  document.getElementById('imagesPerVal').textContent = p.imagesPerProduct;
  if (p.outputSize) {
    document.getElementById('imageWidth').value = p.outputSize;
    document.getElementById('imageHeight').value = p.outputSize;
  }
  document.querySelectorAll('.chip').forEach(c =>
    c.classList.toggle('active', c.dataset.preset === name));
}

// ─── Input helpers ──────────────────────────────────────────────────
const productInput = document.getElementById('productInput');
productInput.addEventListener('input', updateLineCount);

function updateLineCount() {
  const lines = productInput.value.trim().split('\n').filter(l => l.trim());
  document.getElementById('lineCount').textContent =
    `${lines.length} produs${lines.length !== 1 ? 'e' : ''}`;
  // Enable reset when there's any input or results
  const hasContent = lines.length > 0 ||
    document.getElementById('progressSection').classList.contains('active');
  document.getElementById('resetBtn').disabled = !hasContent;
}

function clearInput() {
  productInput.value = '';
  fileProducts = [];
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

    fileProducts = data.products;
    badge.innerHTML = `
      <span class="file-info"><strong>${escapeHtml(file.name)}</strong> &mdash; ${data.count} produse</span>
      <button class="btn-remove" onclick="clearInput()" title="Elimină"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>`;

    productInput.value = data.products.join('\n');
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
    min_resolution:     +document.getElementById('minResolution').value,
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
    min_aspect_ratio:   +document.getElementById('minAspectRatio').value,
    max_aspect_ratio:   +document.getElementById('maxAspectRatio').value,
    priority_sites:     prioritySites,
  };
}

// ─── Toggle advanced ────────────────────────────────────────────────
function toggleAdvanced(el) {
  el.classList.toggle('open');
  document.getElementById('advancedSection').classList.toggle('open');
}

// ─── Timer ──────────────────────────────────────────────────────────
function startTimer() {
  timerStart = Date.now();
  updateTimerDisplay();
  timerInterval = setInterval(updateTimerDisplay, 1000);
}

function stopTimer() {
  if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

function updateTimerDisplay() {
  if (!timerStart) return;
  const elapsed = Math.floor((Date.now() - timerStart) / 1000);
  const m = Math.floor(elapsed / 60);
  const s = elapsed % 60;
  document.getElementById('timerDisplay').textContent =
    `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDuration(ms) {
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}

// ─── Start / Stop ───────────────────────────────────────────────────
async function startScraping() {
  const text = productInput.value.trim();
  if (!text) { alert('Adaugă produse mai întâi!'); return; }

  const lines = text.split('\n').filter(l => l.trim());
  const products = lines.map((line, i) => ({ id: String(i + 1), denumire: line.trim() }));
  const config = getConfig();

  // Reset UI
  stats = { total: products.length, done: 0, success: 0, failed: 0, images: 0 };
  document.getElementById('progressSection').classList.add('active');
  document.getElementById('resultsSection').classList.remove('active');
  document.getElementById('resultsGrid').innerHTML = '';
  document.getElementById('logContainer').innerHTML = '';
  document.getElementById('startBtn').disabled = true;
  document.getElementById('startBtn').style.display = 'none';
  document.getElementById('stopBtn').style.display = 'block';
  document.getElementById('stopBtn').disabled = false;
  document.getElementById('stopBtn').innerHTML = '<i data-lucide="square" style="width:16px;height:16px;"></i> Oprește';
  document.getElementById('resetBtn').disabled = true;
  if (typeof lucide !== 'undefined') lucide.createIcons();
  startTimer();
  updateStats();

  try {
    const resp = await fetch('/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ products, config }),
    });
    const data = await resp.json();
    if (data.error) { alert(data.error); resetBtn(); return; }

    currentJobId = data.job_id;
    listenToEvents(data.job_id);
  } catch (err) {
    alert('Failed to start: ' + err.message);
    resetBtn();
  }
}

function resetBtn() {
  document.getElementById('startBtn').disabled = false;
  document.getElementById('startBtn').innerHTML = '<i data-lucide="play" style="width:16px;height:16px;"></i> Pornește Căutarea';
  if (typeof lucide !== 'undefined') lucide.createIcons();
  document.getElementById('startBtn').style.display = 'block';
  document.getElementById('stopBtn').style.display = 'none';
  document.getElementById('resetBtn').disabled = false;
  stopTimer();
}

async function stopScraping() {
  if (!currentJobId) return;
  try {
    await fetch(`/api/stop/${currentJobId}`, { method: 'POST' });
    addLog('info', 'Se oprește...');
    document.getElementById('stopBtn').disabled = true;
    document.getElementById('stopBtn').textContent = 'Se oprește...';
  } catch (err) {
    console.error('Stop failed:', err);
  }
}

// ─── SSE Events ─────────────────────────────────────────────────────
function listenToEvents(jobId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/stream/${jobId}`);
  eventSource.onmessage = (event) => handleEvent(JSON.parse(event.data));
  eventSource.onerror = () => { eventSource.close(); resetBtn(); };
}

function handleEvent(msg) {
  const { event, data } = msg;

  switch (event) {
    case 'job_start':
      stats.total = data.total_products;
      document.getElementById('statTotal').textContent = stats.total;
      addLog('info', `Job pornit: ${stats.total} produse`);
      break;

    case 'product_start':
      document.getElementById('currentProduct').classList.add('active');
      document.getElementById('currentName').textContent = data.denumire;
      document.getElementById('currentDetail').textContent =
        `Searching... (${data.index + 1}/${data.total})`;
      break;

    case 'search_phase':
      if (data.phase === 'priority') {
        document.getElementById('currentDetail').textContent =
          `Searching ${data.site}... (priority)`;
        addLog('info', `&#128269; Priority: site:${data.site}`);
      } else {
        document.getElementById('currentDetail').textContent = 'Căutare generală...';
        addLog('info', `&#128269; General search`);
      }
      break;

    case 'status':
      addLog('info', data.message || '');
      break;

    case 'candidate_checked': {
      const icon = data.passed ? '&#10003;' : '&#10007;';
      const cls = data.passed ? 'pass' : 'fail';
      const relLabel = data.relevance_score != null ? ` | Relevance: ${data.relevance_score}` : '';
      addLog(cls, `${icon} Quality: ${data.quality_score}${relLabel} ${data.reasons.length ? '- ' + data.reasons.join(', ') : '- OK'}`);
      break;
    }

    case 'product_done':
      stats.done++;
      if (data.status === 'ok') stats.success++;
      else stats.failed++;
      stats.images += (data.images || []).length;
      updateStats();
      addResultCard(data);
      addLog(data.status === 'ok' ? 'pass' : 'fail',
        `${data.denumire}: ${data.images?.length || 0} images (${data.source})`);
      break;

    case 'job_done': {
      document.getElementById('currentProduct').classList.remove('active');
      const duration = timerStart ? formatDuration(Date.now() - timerStart) : '';
      const avgTime = (timerStart && stats.total > 0)
        ? (((Date.now() - timerStart) / 1000) / stats.total).toFixed(1) + 's/product' : '';
      document.getElementById('progressLabel').textContent =
        `Finalizat! ${duration}` + (avgTime ? ` (${avgTime})` : '');
      addLog('info', `Gata! ${data.stats?.images_saved || 0} imagini salvate în ${duration}. ${avgTime}`);
      resetBtn();
      document.getElementById('resetBtn').disabled = false;
      if (eventSource) eventSource.close();
      break;
    }

    case 'heartbeat':
      break;
  }
}

// ─── UI Updates ─────────────────────────────────────────────────────
function updateStats() {
  document.getElementById('statTotal').textContent = stats.total;
  document.getElementById('statDone').textContent = stats.done;
  document.getElementById('statSuccess').textContent = stats.success;
  document.getElementById('statFailed').textContent = stats.failed;

  const pct = stats.total > 0 ? Math.round((stats.done / stats.total) * 100) : 0;
  document.getElementById('progressBar').style.width = pct + '%';
  document.getElementById('progressPercent').textContent = pct + '%';
  document.getElementById('progressLabel').textContent =
    `${stats.done}/${stats.total} procesate (${stats.images} imagini)`;
}

function addLog(cls, html) {
  const container = document.getElementById('logContainer');
  const now = new Date().toLocaleTimeString('ro-RO', {
    hour: '2-digit', minute: '2-digit', second: '2-digit'
  });
  container.innerHTML += `<div class="log-entry ${cls}"><span class="time">${now}</span>${html}</div>`;
  container.scrollTop = container.scrollHeight;
}

function addResultCard(data) {
  document.getElementById('resultsSection').classList.add('active');
  const grid = document.getElementById('resultsGrid');

  let imagesHtml = '';
  if (data.images && data.images.length > 0) {
    data.images.forEach(img => {
      if (img.thumbnail) {
        imagesHtml += `<img class="result-img" src="data:image/jpeg;base64,${img.thumbnail}" title="Score: ${img.quality_score}">`;
      }
    });
  } else {
    imagesHtml = '<div class="no-images-placeholder">Nicio imagine găsită</div>';
  }

  const statusCls = data.status === 'ok' ? 'ok' : 'failed';
  const statusText = data.status === 'ok' ? `${data.images.length} img` : 'Failed';

  grid.innerHTML += `
    <div class="result-card">
      <div class="result-header">
        <div class="result-name">${escapeHtml(data.denumire)}</div>
        <div class="result-status ${statusCls}">${statusText}</div>
      </div>
      <div class="result-images">${imagesHtml}</div>
      <div class="result-meta">
        ${data.images?.[0]?.image_domain ? `<span class="badge">${data.images[0].image_domain}</span>` : `<span class="badge">${data.source || '-'}</span>`}
        ${data.images?.[0]?.quality_score ? `<span class="badge">Q:${data.images[0].quality_score}</span>` : ''}
        ${data.images?.[0]?.relevance_score != null ? `<span class="badge">R:${data.images[0].relevance_score}</span>` : ''}
      </div>
    </div>`;
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ─── Reset All ──────────────────────────────────────────────────────
function resetAll() {
  // Clear inputs
  clearInput();
  document.getElementById('prioritySites').value = '';
  updateSiteCount();

  // Reset config to High Quality defaults
  applyPreset('quality');

  // Reset other fields
  document.getElementById('searchSuffix').value = 'product photo';
  document.getElementById('outputFormat').value = 'jpeg';
  document.getElementById('quality').value = 90;
  document.getElementById('qualityVal').textContent = '90';
  document.getElementById('qualityGroup').style.display = 'block';
  document.getElementById('removeBg').checked = false;
  document.getElementById('pexelsKey').value = '';
  document.getElementById('bingKey').value = '';
  document.getElementById('minAspectRatio').value = 0.4;
  document.getElementById('minAspectVal').textContent = '0.4';
  document.getElementById('maxAspectRatio').value = 2.5;
  document.getElementById('maxAspectVal').textContent = '2.5';

  // Hide progress and results
  document.getElementById('progressSection').classList.remove('active');
  document.getElementById('resultsSection').classList.remove('active');
  document.getElementById('resultsGrid').innerHTML = '';
  document.getElementById('logContainer').innerHTML = '';
  document.getElementById('timerDisplay').textContent = '00:00';
  timerStart = null;

  // Switch to text tab
  switchTab('text');

  // Disable reset again (nothing to reset)
  document.getElementById('resetBtn').disabled = true;
}

// ─── Theme ──────────────────────────────────────────────────────────
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon(next);
}

function updateThemeIcon(theme) {
  document.getElementById('themeIconLight').style.display = theme === 'light' ? 'block' : 'none';
  document.getElementById('themeIconDark').style.display = theme === 'dark' ? 'block' : 'none';
  if (typeof lucide !== 'undefined') lucide.createIcons();
}

(function() {
  const saved = localStorage.getItem('theme') || 'dark';
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
  updateThemeIcon(saved);
})();

// ─── Init ───────────────────────────────────────────────────────────
updateLineCount();
