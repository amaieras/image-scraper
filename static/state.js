// ─── Shared State ───────────────────────────────────────────────────
// All global state lives here so every module can access it.

let currentJobId = null;
let eventSource = null;
let stats = { total: 0, done: 0, success: 0, failed: 0, images: 0 };
let activeTab = 'text';
let fileProducts = [];
let fileHasIds = false;
let timerInterval = null;
let timerStart = null;

// Approval state
// pendingImages: { "filename": { filename, productId, denumire, selected, thumbnail, imageUrl } }
let pendingImages = {};
let approvalDone = false;

// ─── Utilities ──────────────────────────────────────────────────────

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatDuration(ms) {
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}m ${s}s`;
}
