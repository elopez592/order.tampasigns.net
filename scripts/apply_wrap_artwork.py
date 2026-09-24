"""Guarded, frontend-only migration to direct artwork uploads for wraps."""
from pathlib import Path

pending = {}
def edit(filename, changes):
    path = Path(filename)
    body = path.read_text(encoding='utf-8')
    for old, new in changes:
        if body.count(old) != 1:
            raise RuntimeError(f'Expected one anchor in {filename}: {old[:100]}')
        body = body.replace(old, new, 1)
    pending[path] = body

edit('app/static/shop.js', [
    ("import {createWindowUploads} from './window-upload.js?v=20260924-1';", "import {createWindowUploads, usesDirectArtwork} from './window-upload.js?v=20260924-wrap-artwork';"),
    ('  const multiPanelArtwork=p=>!!p?.config?.supports_multiple_dimensions;', '  const multiPanelArtwork=p=>!!p?.config?.supports_multiple_dimensions;\n  const wrapArtworkNote=\'<div class="notice info mt"><strong>Have a design for your wrap?</strong><br>Upload your finished artwork, logo, concept or reference photos. Name separate files for each side or panel. Need artwork created? Request design help and we will review the scope with you.</div>\';'),
    ("if(multiPanelArtwork(p))f.insertAdjacentHTML('afterend',`${multiPanelNote}", "if(usesDirectArtwork(p))f.insertAdjacentHTML('afterend',`${p.config.is_wrap?wrapArtworkNote:multiPanelNote}"),
    ('if(multiPanelArtwork(p))return `${windowUploads.button(project[index])}', 'if(usesDirectArtwork(p))return `${windowUploads.button(project[index])}'),
    ("    if(multiPanelArtwork(p))return '<p class=\"field-hint mt\">For multiple panes", "    if(p?.config.is_wrap)return '<p class=\"field-hint mt\">Upload your wrap artwork, logo or references. Label separate files by side or panel; we will review fit and placement before production.</p>';\n    if(multiPanelArtwork(p))return '<p class=\"field-hint mt\">For multiple panes"),
    ("if(multiPanelArtwork(p)){toast('For multiple panes or full storefronts, upload a concept or request design help so the shop can split and align the artwork.',true);return;}", "if(usesDirectArtwork(p)){toast('For wraps or multiple panes, use Upload Design or Request design help.',true);return;}")
])
edit('app/static/window-upload.js', [
    ('// Keep window artwork in this browser', '// Keep window and wrap artwork in this browser'),
    ('export function createWindowUploads(ctx) {', "// Retain storage keys and record kinds so existing window attachments stay valid.\nexport function usesDirectArtwork(p) {\n  const config = p?.config;\n  return !!(config && (config.is_wrap || config.supports_multiple_dimensions) && !config.artwork_upload_disabled);\n}\n\nexport function createWindowUploads(ctx) {"),
    ("  const supported = id => {\n    const config = product(id)?.config;\n    return !!config?.supports_multiple_dimensions && !config.artwork_upload_disabled;\n  };", "  const supported = id => usesDirectArtwork(product(id));"),
    ("    const shared = key ? getProject().filter(line => line.window_artwork_id === id).length : 0;", "    const shared = key ? getProject().filter(line => line.window_artwork_id === id).length : 0;\n    const wrap = !!product(productId)?.config?.is_wrap;\n    const intro = wrap ? 'Upload your finished wrap artwork, logo, concept or reference photos.' : 'Upload finished artwork, a storefront concept, a sketch or reference photos.';\n    const instructions = wrap ? 'Attach one PDF or separate files named for each side or panel, such as Driver Side, Passenger Side and Rear. We will review fit, placement and production layout.' : 'For multiple panes, attach a multi-page PDF or separate files named for each pane, such as Left Window, Door and Right Window. We will review the layout before production.';"),
    ('<p>Upload finished artwork, a storefront concept, a sketch or reference photos.</p><p class="field-hint">For multiple panes, attach a multi-page PDF or separate files named for each pane, such as Left Window, Door and Right Window. We will review the layout before production.</p>', '<p>${esc(intro)}</p><p class="field-hint">${esc(instructions)}</p>'),
    ('These files are shared by ${shared} panes in this project.', "These files are shared by ${shared} ${wrap ? 'items' : 'panes'} in this project."),
    ('They will be sent to Tampa Signs when you submit your project. No Canva account is needed.', "They will be sent to Tampa Signs when you submit your project.${wrap ? '' : ' No Canva account is needed.'}"),
    ('Saved window artwork is missing.', 'Saved artwork is missing.'),
    ("    let count = 0;", "    let count = 0;\n    const artworkLabel = items.some(item => item.window_artwork_id && product(item.product_id)?.config?.is_wrap) ? 'design' : 'window design';"),
    ("${count} window design file${count === 1 ? '' : 's'} already attached.", "${count} ${artworkLabel} file${count === 1 ? '' : 's'} already attached.")
])
edit('app/static/app.js', [
    ('./shop.js?v=20260924-window-upload', './shop.js?v=20260924-wrap-artwork'),
    ("${cfg.supports_multiple_dimensions?'Multiple window designs are welcome. Attach separate pane files or a multi-page PDF.':'One design per order.'}", "${cfg.is_wrap?'Attach wrap artwork, logos or reference files using Upload Design.':cfg.supports_multiple_dimensions?'Multiple window designs are welcome. Attach separate pane files or a multi-page PDF.':'One design per order.'}")
])
edit('app/static/index.html', [('/static/app.js?v=20260924-window-upload', '/static/app.js?v=20260924-wrap-artwork')])
for path, body in pending.items():
    path.write_text(body, encoding='utf-8')
print('Updated wrap product/cart artwork choices and upload copy; no pricing or backend changes.')
