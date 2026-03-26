// ─── Replace Image ──────────────────────────────────────────────────
// Depends on: state.js (pendingImages, approvalDone, currentJobId, escapeHtml)
// Depends on: approval.js (toggleImageSelect, showApprovalToolbar, updateApprovalCount)
// Depends on: ui.js (openLightbox)

function toggleReplaceForm(cardId) {
  const form = document.getElementById(`replace-${cardId}`);
  if (!form) return;
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

async function submitReplace(cardId, mode) {
  const card = document.getElementById(cardId);
  if (!card) return;
  const productId = card.dataset.productId;
  const denumire = card.dataset.denumire;
  const statusEl = document.getElementById(`replaceStatus-${cardId}`);

  let body = { job_id: currentJobId, product_id: productId, denumire };

  if (mode === 'url') {
    const urlInput = document.getElementById(`replaceUrl-${cardId}`);
    const url = urlInput.value.trim();
    if (!url) { urlInput.focus(); return; }
    body.image_url = url;
    statusEl.textContent = 'Se descarcă imaginea...';
    statusEl.className = 'replace-status loading';
  } else {
    const siteInput = document.getElementById(`replaceSite-${cardId}`);
    const site = siteInput.value.trim();
    if (!site) { siteInput.focus(); return; }
    body.search_site = site;
    statusEl.textContent = `Se caută pe ${site}...`;
    statusEl.className = 'replace-status loading';
  }

  try {
    const resp = await fetch('/api/replace', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await resp.json();

    if (data.ok && data.image) {
      const img = data.image;
      // Add image to the card's images container
      const imagesDiv = card.querySelector('.result-images');
      const placeholder = imagesDiv.querySelector('.no-images-placeholder');
      if (placeholder) placeholder.remove();

      // Radio behavior FIRST: deselect all existing images in this card
      imagesDiv.querySelectorAll('.img-wrapper').forEach(function(w) {
        var fname = w.dataset.filename;
        if (pendingImages[fname]) {
          pendingImages[fname].selected = false;
        }
        var cb = w.querySelector('.img-check-box');
        var lbl = w.querySelector('.img-check-text');
        if (cb) {
          cb.classList.remove('checked', 'approved-icon', 'rejected-icon');
        }
        if (lbl) lbl.textContent = 'Respinsă';
        w.classList.remove('approved');
        w.classList.add('deselected');
      });

      // NOW register new image (AFTER radio, so it can't be accidentally deselected)
      pendingImages[img.filename] = {
        filename: img.filename,
        productId,
        denumire,
        selected: true,
        thumbnail: img.thumbnail,
        imageUrl: img.image_url,
      };

      // Now add the new image wrapper
      var wrapper = document.createElement('div');
      wrapper.className = 'img-wrapper';
      wrapper.dataset.filename = img.filename;

      var imgContainer = document.createElement('div');
      imgContainer.className = 'img-container';

      var imgEl = document.createElement('img');
      imgEl.className = 'result-img';
      imgEl.src = 'data:image/jpeg;base64,' + img.thumbnail;
      imgEl.title = denumire;
      imgEl.onclick = function(e) { e.stopPropagation(); openLightbox(img.image_url); };
      imgContainer.appendChild(imgEl);

      var zoomHint = document.createElement('div');
      zoomHint.className = 'img-zoom-hint';
      zoomHint.innerHTML = '&#128269;';
      imgContainer.appendChild(zoomHint);

      wrapper.appendChild(imgContainer);

      var label = document.createElement('label');
      label.className = 'img-approve-label';
      label.onclick = function(e) { toggleImageSelect(wrapper, e); };
      label.innerHTML = '<span class="img-check-box checked"></span><span class="img-check-text">Salvează</span>';
      wrapper.appendChild(label);

      imagesDiv.appendChild(wrapper);

      // Update status badge
      const statusBadge = card.querySelector('.result-status');
      if (statusBadge) {
        statusBadge.className = 'result-status ok';
        const count = imagesDiv.querySelectorAll('.img-wrapper').length;
        statusBadge.textContent = `${count} img`;
      }

      statusEl.textContent = 'Imaginea a fost adăugată!';
      statusEl.className = 'replace-status success';

      // If approval was already done, re-enable it for new images
      if (approvalDone) {
        approvalDone = false;
        const approveBtn = document.getElementById('approveBtn');
        if (approveBtn) {
          approveBtn.disabled = false;
          approveBtn.textContent = 'Salvează pozele noi';
          approveBtn.classList.remove('done');
        }
        document.getElementById('approvalActions')?.classList.remove('hidden');

        // Remove old rejected/approved wrappers from pendingImages
        document.querySelectorAll('.img-wrapper.rejected, .img-wrapper.approved').forEach(w => {
          const fname = w.dataset.filename;
          if (fname) delete pendingImages[fname];
        });
      }
      // Force the new image to be selected (in case something reset it)
      pendingImages[img.filename].selected = true;

      showApprovalToolbar();
      updateApprovalCount();

      // Hide form after short delay
      setTimeout(() => {
        const form = document.getElementById(`replace-${cardId}`);
        if (form) form.style.display = 'none';
        statusEl.textContent = '';
      }, 1500);

    } else {
      statusEl.textContent = data.error || 'Eroare necunoscută';
      statusEl.className = 'replace-status error';
    }
  } catch (err) {
    statusEl.textContent = 'Eroare: ' + err.message;
    statusEl.className = 'replace-status error';
  }
}
