// Keep customer artwork in this browser until the project is submitted through
// the existing private order upload pipeline. No Canva connection is required.
export const MAX_WINDOW_FILE_BYTES = 50 * 1024 * 1024;

export function validateWindowFiles(files) {
  for (const file of files) {
    if (!file || !/\.(png|jpe?g|pdf)$/i.test(file.name || '')) {
      throw new Error('Choose PDF, PNG or JPG files. Export other design formats to PDF first.');
    }
    if (!file.size || file.size > MAX_WINDOW_FILE_BYTES) {
      throw new Error('Each artwork file must be non-empty and no larger than 50 MB.');
    }
  }
}

// Retain storage keys and record kinds so existing window attachments stay valid.
export function usesDirectArtwork(p) {
  const config = p?.config;
  return !!(config && (config.is_wrap || config.supports_multiple_dimensions) && !config.artwork_upload_disabled);
}

// Standard products offer uploads alongside Canva; specialized contour artwork
// keeps its existing preview flow, and no-artwork products never accept files.
export function supportsArtworkUpload(p) {
  return !!p?.config && !p.config.artwork_upload_disabled && !p.config.contour_customizer;
}

export function createWindowUploads(ctx) {
  const {esc, showModal, toast, getDesign, saveDesign, product, getProject, persist} = ctx;
  const draftId = id => `window-upload-draft-${Number(id)}`;
  const supported = id => supportsArtworkUpload(product(id));
  const read = async id => {
    const record = await getDesign(id);
    if (record && record.kind !== 'window-upload') throw new Error('This artwork cannot be opened here.');
    return record;
  };
  let active = null, busy = false;

  function button(item) {
    if (!supported(item.product_id)) return '';
    const label = usesDirectArtwork(product(item.product_id)) ? 'Upload Design' : 'Upload File';
    const id = item.key ? item.window_artwork_id : draftId(item.product_id);
    return `<button type="button" class="btn light" data-action="window-upload" data-product-id="${Number(item.product_id)}" ${item.key ? `data-project-key="${esc(item.key)}"` : ''}>${esc(label)}</button><span class="field-hint" data-window-upload-summary="${esc(id || '')}" aria-live="polite">${id ? 'Checking saved artwork...' : 'No artwork attached yet'}</span>`;
  }

  async function refresh() {
    for (const element of document.querySelectorAll('[data-window-upload-summary]')) {
      const id = element.dataset.windowUploadSummary;
      const record = id ? await read(id) : null;
      const count = record?.files?.length || 0;
      element.textContent = count ? `${count} file${count === 1 ? '' : 's'} attached` : 'No artwork attached yet';
    }
  }

  function renderFiles() {
    const target = document.querySelector('#window-upload-files');
    if (!target || !active) return;
    target.innerHTML = active.files.length ? active.files.map((file, index) => `<div class="row between wrap mt-sm"><span style="overflow-wrap:anywhere;min-width:0">${esc(file.name)} <small class="muted">(${(file.size / 1048576).toFixed(2)} MB)</small></span><button type="button" class="btn light small" data-action="window-upload-remove" data-index="${index}" aria-label="Remove ${esc(file.name)}">Remove</button></div>`).join('') : '<p class="muted">No files selected yet.</p>';
  }

  async function save(files) {
    if (busy) throw new Error('Artwork is still saving. Please try again.');
    busy = true;
    const target = active, input = document.querySelector('#window-upload-input');
    if (input) input.disabled = true;
    try {
      await saveDesign({id: target.id, kind: 'window-upload', product_id: target.productId, files});
      if (target.key) {
        const item = getProject().find(line => line.key === target.key);
        if (!item) throw new Error('This item was removed. Please reopen your project.');
        item.window_artwork_id = target.id;
        persist();
        document.querySelectorAll('[data-project-key]').forEach(button => {
          if (button.dataset.projectKey === target.key) {
            const summary = button.nextElementSibling;
            if (summary?.hasAttribute('data-window-upload-summary')) summary.dataset.windowUploadSummary = target.id;
          }
        });
      }
      target.files = files;
      if (active === target) renderFiles();
      await refresh();
    } finally {
      busy = false;
      if (input?.isConnected) input.disabled = false;
    }
  }

  async function open(button) {
    if (busy) throw new Error('Artwork is still saving. Please try again.');
    const key = button.dataset.projectKey || null;
    const item = key ? getProject().find(line => line.key === key) : null;
    if (key && !item) throw new Error('This item is no longer in your project.');
    const productId = item?.product_id || Number(button.dataset.productId);
    if (!supported(productId)) throw new Error('Artwork upload is not available for this product.');
    const id = key ? item.window_artwork_id || crypto.randomUUID() : draftId(productId);
    const record = await read(id);
    if (item?.window_artwork_id && !record) throw new Error('Saved artwork is missing. Remove and re-add this item to attach it again.');
    active = {id, key, productId, files: [...(record?.files || [])]};
    const shared = key ? getProject().filter(line => line.window_artwork_id === id).length : 0;
    const wrap = !!product(productId)?.config?.is_wrap;
    const panes = !wrap && !!product(productId)?.config?.supports_multiple_dimensions;
    const intro = wrap ? 'Upload your finished wrap artwork, logo, concept or reference photos.' : panes ? 'Upload finished artwork, a storefront concept, a sketch or reference photos.' : 'Upload your ready-to-print artwork, logo or reference files for this product.';
    const instructions = wrap ? 'Attach one PDF or separate files named for each side or panel, such as Driver Side, Passenger Side and Rear. We will review fit, placement and production layout.' : panes ? 'For multiple panes, attach a multi-page PDF or separate files named for each pane, such as Left Window, Door and Right Window. We will review the layout before production.' : 'Attach one file or separate files for each printed side, such as Front and Back. We will review your artwork before production.';
    showModal(wrap || panes ? 'Upload Design' : 'Upload File', `<div class="stack"><p>${esc(intro)}</p><p class="field-hint">${esc(instructions)}</p>${shared > 1 ? `<div class="notice info">These files are shared by ${shared} ${panes ? 'panes' : 'items'} in this project. Changes here apply to the whole group.</div>` : ''}<label class="field"><span>Choose design files</span><input id="window-upload-input" type="file" accept=".png,.jpg,.jpeg,.pdf" multiple></label><p class="field-hint">PDF, PNG or JPG. Up to 50 MB per file. You can select several files or add more afterward.</p><div id="window-upload-error" class="form-error" role="alert"></div><div id="window-upload-files" aria-live="polite"></div><div class="notice info">Files are saved in this browser${key ? ' and attached to your project' : '. After choosing your options, click Add to project'}. They will be sent to Tampa Signs when you submit your project.${wrap ? '' : ' No Canva account is needed.'}</div><div class="row mt"><button type="button" class="btn primary" data-action="close">Done</button></div></div>`);
    renderFiles();
    document.querySelector('#window-upload-input').onchange = async event => {
      const selected = [...event.target.files], error = document.querySelector('#window-upload-error');
      if (error) error.textContent = '';
      try {
        validateWindowFiles(selected);
        const files = [...active.files];
        for (const file of selected) {
          if (!files.some(saved => saved.name === file.name && saved.size === file.size && saved.lastModified === file.lastModified)) files.push(file);
        }
        if (selected.length) {
          await save(files);
          toast(`${files.length} design file${files.length === 1 ? '' : 's'} saved${key ? ' to your project' : ' for this product'}.`);
        }
      } catch (e) {
        if (error?.isConnected) error.textContent = e.message;
        else toast(e.message, true);
      } finally { event.target.value = ''; }
    };
  }

  async function prepareItems(items) {
    if (busy) throw new Error('Artwork is still saving. Please try Add to project again.');
    const snapshots = new Map();
    for (const item of items) {
      if (!supported(item.product_id) || snapshots.has(Number(item.product_id))) continue;
      const record = await read(draftId(item.product_id));
      if (record?.files?.length) {
        const id = crypto.randomUUID();
        await saveDesign({...record, id});
        snapshots.set(Number(item.product_id), id);
      }
    }
    return items.map(item => snapshots.has(Number(item.product_id)) ? {...item, window_artwork_id: snapshots.get(Number(item.product_id))} : item);
  }

  async function clearDrafts(items) {
    for (const id of new Set(items.filter(item => item.window_artwork_id).map(item => Number(item.product_id)))) {
      await saveDesign({id: draftId(id), kind: 'window-upload', product_id: id, files: []});
    }
    await refresh();
  }

  async function filesFor(items) {
    if (busy) throw new Error('Artwork is still saving. Please submit your project again after it finishes.');
    const files = [], seen = new Set();
    for (const item of items) {
      const id = item.window_artwork_id;
      if (!id || seen.has(id) || !supported(item.product_id)) continue;
      seen.add(id);
      const record = await read(id);
      if (!record) throw new Error('Saved artwork is missing. Reattach it before submitting your project.');
      validateWindowFiles(record.files || []);
      const lines = items.map((line, index) => line.window_artwork_id === id ? index + 1 : null).filter(Boolean);
      for (const file of record.files || []) {
        const name = file.name.replace(/[\\/]/g, '-'), extension = name.slice(name.lastIndexOf('.'));
        const prefix = `items-${lines.join('-')}-`;
        const stem = name.slice(0, -extension.length).slice(0, Math.max(10, 175 - prefix.length - extension.length));
        const type = /\.pdf$/i.test(name) ? 'application/pdf' : /\.png$/i.test(name) ? 'image/png' : 'image/jpeg';
        files.push(new File([file], prefix + stem + extension, {type, lastModified: file.lastModified}));
      }
    }
    return files;
  }

  async function checkoutHint(items) {
    const attached = items.filter(item => item.window_artwork_id && supported(item.product_id));
    const ids = new Set(attached.map(item => item.window_artwork_id));
    let count = 0;
    const artworkLabel = attached.length && attached.every(item => product(item.product_id)?.config?.supports_multiple_dimensions && !product(item.product_id)?.config?.is_wrap) ? 'window design' : 'design';
    for (const id of ids) count += (await read(id))?.files?.length || 0;
    const input = document.querySelector('form[data-form="public-order"] input[name="artwork"]');
    if (count && input && !document.querySelector('#window-upload-checkout-notice')) {
      input.closest('label').insertAdjacentHTML('beforebegin', `<div id="window-upload-checkout-notice" class="notice good">${count} ${artworkLabel} file${count === 1 ? '' : 's'} already attached. These will be included automatically when you submit. Use the field below only for additional artwork.</div>`);
    }
  }

  return {button, refresh, prepareItems, clearDrafts, filesFor, checkoutHint, actions: {
    'window-upload': open,
    'window-upload-remove': async button => {
      const index = Number(button.dataset.index);
      if (!active || !Number.isInteger(index) || index < 0 || index >= active.files.length) return;
      await save(active.files.filter((_, i) => i !== index));
    }
  }};
}
