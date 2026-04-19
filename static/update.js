// ─── Auto-Update ─────────────────────────────────────────────────────────

/** Load current version on page load */
document.addEventListener('DOMContentLoaded', () => {
  fetch('/api/version')
    .then(r => r.json())
    .then(d => {
      document.getElementById('versionText').textContent = d.version || '?';
    })
    .catch(() => {});

  // Auto-check for updates after 5s, then every 5 minutes
  setTimeout(checkForUpdate, 5000);
  setInterval(checkForUpdate, 5 * 60 * 1000);
});

/** Check GitHub for a newer release and load version list */
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
        loadVersionList();
      } else {
        badge.classList.remove('has-update');
        badge.title = `v${data.current_version} - up to date (click for version list)`;
        if (!_manualPickerOpen) {
          banner.style.display = 'none';
        }
      }
    })
    .catch(() => {
      badge.title = 'Update check failed - click to retry';
    });
}

let _manualPickerOpen = false;

/** Show version picker (click on version badge) */
function showVersionPicker() {
  const banner = document.getElementById('updateBanner');
  const msg = document.getElementById('updateMessage');
  _manualPickerOpen = true;
  banner.style.display = 'flex';
  msg.textContent = 'Select version:';
  loadVersionList();
  checkForUpdate();
}

/** Load available versions into the dropdown */
function loadVersionList() {
  const select = document.getElementById('versionSelect');
  const previousValue = select.value;  // preserve user's selection

  fetch('/api/versions')
    .then(r => r.json())
    .then(data => {
      if (!data.versions || data.versions.length === 0) return;

      select.innerHTML = '';
      data.versions.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.version;
        const label = v.current ? `v${v.version} (current)` : `v${v.version}`;
        const date = v.date ? ` - ${v.date.split('T')[0]}` : '';
        opt.textContent = label + date;
        if (v.current) {
          opt.disabled = true;
          opt.selected = true;
        }
        select.appendChild(opt);
      });
      // Restore previous selection, or select first non-current version
      if (previousValue) {
        const exists = [...select.options].some(o => o.value === previousValue && !o.disabled);
        if (exists) select.value = previousValue;
      } else {
        const firstAvailable = [...select.options].find(o => !o.disabled);
        if (firstAvailable) select.value = firstAvailable.value;
      }
      select.style.display = 'inline-block';
    })
    .catch(() => {});
}

/** Download & apply update from GitHub, then wait for restart */
function applyUpdate() {
  const btn = document.getElementById('updateBtn');
  const msg = document.getElementById('updateMessage');
  const select = document.getElementById('versionSelect');
  const selectedVersion = select.value || null;

  btn.disabled = true;
  btn.textContent = 'Updating...';
  msg.textContent = selectedVersion
    ? `Downloading v${selectedVersion}...`
    : 'Downloading latest update...';

  fetch('/api/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: selectedVersion }),
  })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        msg.textContent = `Updated to v${data.updated_to}! Restarting...`;
        btn.style.display = 'none';
        select.style.display = 'none';
        waitForRestart();
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

/** Poll the server until it comes back after restart, then reload */
function waitForRestart() {
  const msg = document.getElementById('updateMessage');
  let dots = 0;

  const poll = setInterval(() => {
    dots = (dots + 1) % 4;
    msg.textContent = 'Restarting' + '.'.repeat(dots + 1);

    fetch('/api/version', { cache: 'no-store' })
      .then(r => r.json())
      .then(() => {
        clearInterval(poll);
        msg.textContent = 'Reloading...';
        setTimeout(() => window.location.reload(true), 500);
      })
      .catch(() => {}); // Server still down, keep polling
  }, 2000);
}
