// ─── Scraper: Start / Stop / SSE / Results ──────────────────────────
// Depends on: state.js (all shared state + escapeHtml, formatDuration)
// Depends on: approval.js (showApprovalToolbar, hideApprovalToolbar)
// Depends on: ui.js (addLog, updateStats, openLightbox)

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

// ─── Start / Stop ───────────────────────────────────────────────────

async function startScraping() {
  const text = document.getElementById('productInput').value.trim();
  if (!text) { alert('Adaugă produse mai întâi!'); return; }

  const lines = text.split('\n').filter(l => l.trim());
  const products = lines.map((line, i) => ({ id: String(i + 1), denumire: line.trim() }));
  const config = getConfig();

  // Reset UI + approval state
  stats = { total: products.length, done: 0, success: 0, failed: 0, images: 0 };
  pendingImages = {};
  approvalDone = false;
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
  hideApprovalToolbar();
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
      if (Object.keys(pendingImages).length > 0) {
        showApprovalToolbar();
      }
      break;
    }

    case 'heartbeat':
      break;
  }
}

// ─── Result Cards ───────────────────────────────────────────────────

function addResultCard(data) {
  document.getElementById('resultsSection').classList.add('active');
  const grid = document.getElementById('resultsGrid');

  let imagesHtml = '';
  if (data.images && data.images.length > 0) {
    data.images.forEach(img => {
      if (img.thumbnail) {
        const imgUrl = img.image_url || '';
        const fname = img.filename || '';
        // Register in pendingImages
        pendingImages[fname] = {
          filename: fname,
          productId: data.product_id,
          denumire: data.denumire,
          selected: true,
          thumbnail: img.thumbnail,
          imageUrl: imgUrl,
        };
        imagesHtml += `
          <div class="img-wrapper" data-filename="${escapeHtml(fname)}">
            <div class="img-container">
              <img class="result-img" src="data:image/jpeg;base64,${img.thumbnail}" title="${escapeHtml(data.denumire)}" onclick="event.stopPropagation(); openLightbox('${imgUrl.replace(/'/g, "\\'")}')">
              <div class="img-zoom-hint">&#128269;</div>
              <button class="img-download-btn" onclick="event.stopPropagation(); downloadSingleImage('${imgUrl.replace(/'/g, "\\'")}', '${escapeHtml(fname).replace(/'/g, "\\'")}')" title="Descarcă imaginea"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg></button>
            </div>
            <label class="img-approve-label" onclick="toggleImageSelect(this.closest('.img-wrapper'), event)">
              <span class="img-check-box checked"></span>
              <span class="img-check-text">Salvează</span>
            </label>
          </div>`;
      }
    });
  } else {
    imagesHtml = '<div class="no-images-placeholder">Nicio imagine găsită</div>';
  }

  const statusCls = data.status === 'ok' ? 'ok' : 'failed';
  const statusText = data.status === 'ok' ? `${data.images.length} img` : 'Failed';

  const cardId = `card-${data.product_id || idx}`;
  grid.innerHTML += `
    <div class="result-card" id="${cardId}" data-product-id="${escapeHtml(data.product_id || '')}" data-denumire="${escapeHtml(data.denumire)}">
      <div class="result-header">
        <div class="result-name">${escapeHtml(data.denumire)}<button class="copy-name-btn" title="Copiază numele" onclick="copyProductName(this, '${escapeHtml(data.denumire).replace(/'/g, "\\'")}')"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button></div>
        <div class="result-status ${statusCls}">${statusText}</div>
      </div>
      <div class="result-images">${imagesHtml}</div>
      <div class="result-meta">
        ${data.images?.[0]?.image_domain ? `<span class="badge">${data.images[0].image_domain}</span>` : `<span class="badge">${data.source || '-'}</span>`}
        ${data.images?.[0]?.quality_score ? `<span class="badge">Q:${data.images[0].quality_score}</span>` : ''}
        ${data.images?.[0]?.relevance_score != null ? `<span class="badge">R:${data.images[0].relevance_score}</span>` : ''}
        <a class="replace-link" onclick="toggleReplaceForm('${cardId}')">Caută altă poză</a>
      </div>
      <div class="replace-form" id="replace-${cardId}" style="display:none">
        <div class="replace-row">
          <span class="replace-info-icon" data-tip="Click dreapta pe imagine → Copy Image Address / Copiază adresa imaginii. Acceptă și link-uri data:image (base64).">ⓘ</span>
          <input type="text" class="replace-input" id="replaceUrl-${cardId}" placeholder="Lipește link direct la imagine...">
          <button class="btn btn-sm btn-approve" onclick="submitReplace('${cardId}', 'url')">Descarcă</button>
        </div>
        <div class="replace-status" id="replaceStatus-${cardId}"></div>
      </div>
    </div>`;
}
