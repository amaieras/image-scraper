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
