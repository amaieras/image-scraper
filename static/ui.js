// ─── UI: Stats, Logging, Lightbox, Theme, Zoom ─────────────────────
// Depends on: state.js (stats)

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

// ─── Copy Product Name ───────────────────────────────────────────────

function copyProductName(btn, name) {
  navigator.clipboard.writeText(name).then(function() {
    var original = btn.innerHTML;
    btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
    btn.classList.add('copied');
    setTimeout(function() { btn.innerHTML = original; btn.classList.remove('copied'); }, 1500);
  });
}

// ─── Lightbox ────────────────────────────────────────────────────────

function openLightbox(url) {
  if (!url) return;
  let overlay = document.getElementById('lightboxOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'lightboxOverlay';
    overlay.innerHTML = '<img id="lightboxImg" src="">';
    overlay.addEventListener('click', () => overlay.style.display = 'none');
    document.body.appendChild(overlay);
  }
  document.getElementById('lightboxImg').src = url;
  overlay.style.display = 'flex';
}

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    const o = document.getElementById('lightboxOverlay');
    if (o) o.style.display = 'none';
  }
});

// ─── Font Size (zoom-based) ─────────────────────────────────────────

const ZOOM_LEVELS = [0.8, 0.9, 1, 1.1, 1.25, 1.4];
let currentZoomIndex = 2;

function changeFontSize(direction) {
  currentZoomIndex = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, currentZoomIndex + direction));
  applyZoom();
  localStorage.setItem('zoomLevel', currentZoomIndex);
}

function applyZoom() {
  document.documentElement.style.zoom = ZOOM_LEVELS[currentZoomIndex];
}

(function initFontSize() {
  const saved = localStorage.getItem('zoomLevel');
  if (saved !== null) {
    currentZoomIndex = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, +saved));
    applyZoom();
  }
})();

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

// ─── Custom Tooltip (for [data-tip] elements) ───────────────────────

(function() {
  var tip = null;
  document.addEventListener('mouseenter', function(e) {
    var el = e.target.closest('[data-tip]');
    if (!el) return;
    tip = document.createElement('div');
    tip.className = 'custom-tooltip';
    tip.textContent = el.getAttribute('data-tip');
    document.body.appendChild(tip);
    var r = el.getBoundingClientRect();
    tip.style.left = Math.min(r.left, window.innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = (r.top - tip.offsetHeight - 6) + 'px';
    if (parseFloat(tip.style.top) < 4) tip.style.top = (r.bottom + 6) + 'px';
  }, true);
  document.addEventListener('mouseleave', function(e) {
    if (e.target.closest('[data-tip]') && tip) { tip.remove(); tip = null; }
  }, true);
})();
