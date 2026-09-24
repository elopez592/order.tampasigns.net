from pathlib import Path

pending = {}
def edit(filename, changes):
    path = Path(filename)
    text = path.read_text(encoding='utf-8')
    for old, new in changes:
        if text.count(old) != 1:
            raise RuntimeError(f'Expected one patch anchor in {filename}: {old[:90]}')
        text = text.replace(old, new, 1)
    pending[path] = text

edit('app/static/window-upload.js', [
    ('// Keep window and wrap artwork in this browser', '// Keep customer artwork in this browser'),
    ('export function createWindowUploads(ctx) {', '''// Standard products offer uploads alongside Canva; specialized contour artwork
// keeps its existing preview flow, and no-artwork products never accept files.
export function supportsArtworkUpload(p) {
  return !!p?.config && !p.config.artwork_upload_disabled && !p.config.contour_customizer;
}

export function createWindowUploads(ctx) {'''),
    ('  const supported = id => usesDirectArtwork(product(id));', '  const supported = id => supportsArtworkUpload(product(id));'),
    ('  function button(item) {', '''  function button(item) {
    if (!supported(item.product_id)) return '';
    const label = usesDirectArtwork(product(item.product_id)) ? 'Upload Design' : 'Upload File';'''),
    ('}>Upload Design</button><span class="field-hint"', '}>${esc(label)}</button><span class="field-hint"'),
    ("    const intro = wrap ? 'Upload your finished wrap artwork, logo, concept or reference photos.' : 'Upload finished artwork, a storefront concept, a sketch or reference photos.';", "    const panes = !wrap && !!product(productId)?.config?.supports_multiple_dimensions;\n    const intro = wrap ? 'Upload your finished wrap artwork, logo, concept or reference photos.' : panes ? 'Upload finished artwork, a storefront concept, a sketch or reference photos.' : 'Upload your ready-to-print artwork, logo or reference files for this product.';"),
    ("layout.' : 'For multiple panes,", "layout.' : panes ? 'For multiple panes,"),
    ("We will review the layout before production.';", "We will review the layout before production.' : 'Attach one file or separate files for each printed side, such as Front and Back. We will review your artwork before production.';"),
    ("    showModal('Upload Design',", "    showModal(wrap || panes ? 'Upload Design' : 'Upload File',"),
    ("${wrap ? 'items' : 'panes'} in this project.", "${panes ? 'panes' : 'items'} in this project."),
    ('    const ids = new Set(items.map(item => item.window_artwork_id).filter(Boolean));', '    const attached = items.filter(item => item.window_artwork_id && supported(item.product_id));\n    const ids = new Set(attached.map(item => item.window_artwork_id));'),
    ("    const artworkLabel = items.some(item => item.window_artwork_id && product(item.product_id)?.config?.is_wrap) ? 'design' : 'window design';", "    const artworkLabel = attached.length && attached.every(item => product(item.product_id)?.config?.supports_multiple_dimensions && !product(item.product_id)?.config?.is_wrap) ? 'window design' : 'design';")
])
edit('app/static/shop.js', [
    ('./window-upload.js?v=20260924-wrap-artwork', './window-upload.js?v=20260924-all-uploads'),
    ('<div class="row wrap mt"><button type="button" class="btn light" data-action="product-canva">Design in Canva</button></div>', '<div class="row wrap mt"><button type="button" class="btn light" data-action="product-canva">Design in Canva</button>${windowUploads.button({product_id:p.id})}</div>'),
    ('Canva opens in a new tab. Use the selected product size, then upload the exported PDF/PNG when submitting your project.', 'Already have artwork? Use Upload File. Or design in Canva, export PDF Print or a high-resolution PNG, and attach it here.'),
    ('    return canvaButton(line.width,line.height,publicProductName(p));', '    return `${canvaButton(line.width,line.height,publicProductName(p))}${windowUploads.button(project[index])}`;'),
    ('For Canva artwork, download a PDF Print or high-resolution PNG and attach it when you submit this project.', 'Use Upload File to attach finished artwork. For Canva designs, export PDF Print or a high-resolution PNG first. Attached files are included when you submit this project.')
])
edit('app/static/app.js', [('./shop.js?v=20260924-wrap-artwork', './shop.js?v=20260924-all-uploads')])
edit('app/static/index.html', [('/static/app.js?v=20260924-wrap-artwork', '/static/app.js?v=20260924-all-uploads')])
edit('tests/window_upload.test.mjs', [("await assert.rejects(() => reloaded.actions['window-upload']({dataset:{productId:'3'}}), /not available/);", "await assert.doesNotReject(() => reloaded.actions['window-upload']({dataset:{productId:'3'}})); // Ordinary products now support direct upload too.")])
edit('tests/wrap_upload.test.mjs', [("await assert.rejects(()=>reloaded.actions['window-upload']({dataset:{productId:'14'}}),/not available/);", "await assert.doesNotReject(()=>reloaded.actions['window-upload']({dataset:{productId:'14'}})); // Ordinary quantity-based products now accept uploads.")])
for path, text in pending.items():
    path.write_text(text, encoding='utf-8')
print('Applied Upload File alongside Canva. No pricing, DNS, backend or redirect changes.')
