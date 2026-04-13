// ─── Image Selection / Approval ─────────────────────────────────────
// Depends on: state.js (pendingImages, approvalDone, escapeHtml, currentJobId)
// Depends on: ui.js (addLog)

function toggleImageSelect(wrapper, event) {
  if (approvalDone) return;
  event.stopPropagation();
  const fname = wrapper.dataset.filename;
  const checkbox = wrapper.querySelector('.img-check-box');
  const label = wrapper.querySelector('.img-check-text');
  const isSelected = pendingImages[fname]?.selected;

  if (isSelected) {
    // Deselect this image
    pendingImages[fname].selected = false;
    checkbox.classList.remove('checked');
    wrapper.classList.add('deselected');
    if (label) label.textContent = 'Respinsă';
  } else {
    // Select this image — radio: deselect all others in the same card
    const card = wrapper.closest('.result-card');
    if (card) {
      card.querySelectorAll('.img-wrapper').forEach(w => {
        const otherFname = w.dataset.filename;
        if (otherFname === fname) return;
        if (pendingImages[otherFname]) {
          pendingImages[otherFname].selected = false;
        }
        const cb = w.querySelector('.img-check-box');
        const lbl = w.querySelector('.img-check-text');
        if (cb) cb.classList.remove('checked', 'approved-icon', 'rejected-icon');
        if (lbl) lbl.textContent = 'Respinsă';
        w.classList.remove('approved');
        w.classList.add('deselected');
      });
    }
    pendingImages[fname].selected = true;
    checkbox.classList.add('checked');
    wrapper.classList.remove('deselected');
    if (label) label.textContent = 'Salvează';
  }
  updateApprovalCount();
}

function selectAllImages() {
  if (approvalDone) return;
  Object.keys(pendingImages).forEach(fname => {
    pendingImages[fname].selected = true;
  });
  document.querySelectorAll('.img-wrapper').forEach(w => {
    w.classList.remove('deselected');
    const cb = w.querySelector('.img-check-box');
    if (cb) cb.classList.add('checked');
    const lbl = w.querySelector('.img-check-text');
    if (lbl) lbl.textContent = 'Salvează';
  });
  updateApprovalCount();
}

function deselectAllImages() {
  if (approvalDone) return;
  Object.keys(pendingImages).forEach(fname => {
    pendingImages[fname].selected = false;
  });
  document.querySelectorAll('.img-wrapper').forEach(w => {
    w.classList.add('deselected');
    const cb = w.querySelector('.img-check-box');
    if (cb) cb.classList.remove('checked');
    const lbl = w.querySelector('.img-check-text');
    if (lbl) lbl.textContent = 'Respinsă';
  });
  updateApprovalCount();
}

function updateApprovalCount() {
  // Count per product: how many products have at least one selected image
  const productIds = new Set();
  const selectedProductIds = new Set();
  Object.values(pendingImages).forEach(function(p) {
    productIds.add(p.productId);
    if (p.selected) selectedProductIds.add(p.productId);
  });
  const total = productIds.size;
  const selected = selectedProductIds.size;
  const counter = document.getElementById('approvalCount');
  if (counter) {
    counter.textContent = `${selected} / ${total} selectate`;
  }
  const approveBtn = document.getElementById('approveBtn');
  if (approveBtn) {
    approveBtn.disabled = selected === 0;
  }
}

function showApprovalToolbar() {
  const toolbar = document.getElementById('approvalToolbar');
  if (toolbar) {
    toolbar.classList.add('visible');
    updateApprovalCount();
    document.querySelector('.app').style.paddingBottom = '90px';
  }
}

function hideApprovalToolbar() {
  const toolbar = document.getElementById('approvalToolbar');
  if (toolbar) {
    toolbar.classList.remove('visible');
    document.querySelector('.app').style.paddingBottom = '';
  }
}

function resetApprovalToolbar() {
  const approveBtn = document.getElementById('approveBtn');
  if (approveBtn) {
    approveBtn.textContent = 'Aprobă Selecția';
    approveBtn.disabled = false;
    approveBtn.classList.remove('done');
  }
  const actions = document.getElementById('approvalActions');
  if (actions) actions.classList.remove('hidden');
}

async function approveSelected() {
  if (!currentJobId || approvalDone) return;

  const approved = Object.entries(pendingImages)
    .filter(([_, p]) => p.selected)
    .map(([fname, _]) => fname);

  if (approved.length === 0) {
    alert('Selectează cel puțin o imagine!');
    return;
  }

  const approveBtn = document.getElementById('approveBtn');
  approveBtn.disabled = true;
  approveBtn.textContent = 'Se salvează...';

  try {
    const resp = await fetch('/api/approve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: currentJobId, approved }),
    });
    const data = await resp.json();

    if (data.ok) {
      approvalDone = true;
      let logMsg = `Aprobat! ${data.moved} imagini salvate, ${data.deleted} respinse.`;
      if (data.hermes_count > 0) {
        logMsg += ` Hermes: ${data.hermes_count} copii create.`;
      }
      addLog('pass', logMsg);

      // Visual feedback: mark approved cards green, rejected grey
      document.querySelectorAll('.img-wrapper').forEach(w => {
        const fname = w.dataset.filename;
        const cb = w.querySelector('.img-check-box');
        const lbl = w.querySelector('.img-check-text');
        if (pendingImages[fname]?.selected) {
          w.classList.add('approved');
          w.classList.remove('deselected');
          if (cb) { cb.classList.remove('checked'); cb.classList.add('approved-icon'); }
          if (lbl) lbl.textContent = 'Salvată';
        } else {
          w.classList.add('rejected');
          w.classList.remove('deselected');
          if (cb) { cb.classList.remove('checked'); cb.classList.add('rejected-icon'); }
          if (lbl) lbl.textContent = 'Respinsă';
        }
      });

      // Update toolbar to show success
      const hermesInfo = data.hermes_count > 0 ? ` + ${data.hermes_count} Hermes` : '';
      approveBtn.textContent = `${data.moved} imagini salvate${hermesInfo}`;
      approveBtn.classList.add('done');

      // Hide select all / deselect all buttons
      document.getElementById('approvalActions')?.classList.add('hidden');
    } else {
      alert('Eroare: ' + (data.error || 'Unknown error'));
      approveBtn.disabled = false;
      approveBtn.textContent = 'Aprobă Selecția';
    }
  } catch (err) {
    alert('Eroare la salvare: ' + err.message);
    approveBtn.disabled = false;
    approveBtn.textContent = 'Aprobă Selecția';
  }
}

// ─── Download Functions ─────────────────────────────────────────────

function downloadSingleImage(imageUrl, filename) {
  if (!currentJobId) return;
  // Try to download from our server first (cached in _pending or output)
  const serverUrl = `/api/images/${currentJobId}/${filename}`;
  const a = document.createElement('a');
  a.href = serverUrl;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function downloadZip() {
  if (!currentJobId) return;
  const btn = document.getElementById('downloadZipBtn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Se pregătește...';
  }
  try {
    const resp = await fetch(`/api/download-zip/${currentJobId}`);
    if (!resp.ok) throw new Error('ZIP generation failed');
    const blob = await resp.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `images-${currentJobId}.zip`;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  } catch (err) {
    alert('Eroare la descărcare ZIP: ' + err.message);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Descarcă ZIP';
    }
  }
}
