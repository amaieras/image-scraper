// ─── Auto-Update ─────────────────────────────────────────────────────────

/** Load current version on page load */
document.addEventListener('DOMContentLoaded', () => {
  fetch('/api/version')
    .then(r => r.json())
    .then(d => {
      document.getElementById('versionText').textContent = d.version || '?';
    })
    .catch(() => {});

  // Auto-check for updates after 5s
  setTimeout(checkForUpdate, 5000);
});

/** Check GitHub for a newer release */
function checkForUpdate() {
  const badge = document.getElementById('versionBadge');
  const banner = document.getElementById('updateBanner');
  const msg = document.getElementById('updateMessage');

  badge.title = 'Checking for updates...';

  fetch('/api/check-update')
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        badge.title = 'Update check failed - click to retry';
        return;
      }
      if (data.update_available) {
        badge.classList.add('has-update');
        badge.title = `Update available: v${data.latest_version}`;
        msg.textContent = `New version available: v${data.latest_version}`;
        banner.style.display = 'flex';
      } else {
        badge.classList.remove('has-update');
        badge.title = `v${data.current_version} - up to date`;
        banner.style.display = 'none';
      }
    })
    .catch(() => {
      badge.title = 'Update check failed - click to retry';
    });
}

/** Download & apply update from GitHub */
function applyUpdate() {
  const btn = document.getElementById('updateBtn');
  const msg = document.getElementById('updateMessage');

  btn.disabled = true;
  btn.textContent = 'Updating...';
  msg.textContent = 'Downloading update...';

  fetch('/api/update', { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        msg.textContent = `Updated to v${data.updated_to}! Restart the app to apply.`;
        btn.textContent = 'Done';
        btn.style.display = 'none';
      } else {
        msg.textContent = `Update failed: ${data.error}`;
        btn.textContent = 'Retry';
        btn.disabled = false;
      }
    })
    .catch(err => {
      msg.textContent = `Update failed: ${err.message}`;
      btn.textContent = 'Retry';
      btn.disabled = false;
    });
}
