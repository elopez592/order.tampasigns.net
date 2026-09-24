from pathlib import Path

path = Path('app/static/shop.js')
text = path.read_text()

def replace(old, new):
    global text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f'Expected one safe patch anchor, found {count}: {old[:100]}')
    text = text.replace(old, new, 1)

replace('// Customer project cart and artwork attachments.', "import {createWindowUploads} from './window-upload.js?v=20260924-1';\n\n// Customer project cart and artwork attachments.")
replace("  const getDesign=id=>storage('readonly',s=>s.get(id));", "  const getDesign=id=>storage('readonly',s=>s.get(id));\n  const windowUploads=createWindowUploads({esc,showModal,toast,getDesign,saveDesign,product,getProject:()=>project,persist});")
replace("  const multiPanelNote='<div class=\"notice info mt\"><strong>Multi-pane artwork needs shop layout.</strong><br>Upload a concept, sketch or reference files when you submit, or request design help so we can split the artwork cleanly across each pane.</div>';", "  const multiPanelNote='<div class=\"notice info mt\"><strong>Have a design for your windows?</strong><br>Upload finished artwork, a multi-page PDF, or separate files for each pane. You can also upload a storefront concept or request design help. We will review the layout and alignment before production.</div>';")
replace('`${multiPanelNote}<div class="row wrap mt"><button type="button" class="btn light" data-action="design-quote">Request design help</button></div>`', '`${multiPanelNote}<div class="row wrap mt">${windowUploads.button({product_id:p.id})}<button type="button" class="btn light" data-action="design-quote">Request design help</button></div>`')
replace('    }\n  }\n  async function add(){', '    }\n    windowUploads.refresh().catch(e=>toast(e.message,true));\n  }\n  async function add(){')
replace('    project.push(...state.currentQuoteItems.map(item=>({...item,key:crypto.randomUUID()})));persist();', '    const items=await windowUploads.prepareItems(state.currentQuoteItems.map(item=>({...item,key:crypto.randomUUID()})));\n    project.push(...items);persist();\n    await windowUploads.clearDrafts(items).catch(e=>toast(e.message,true));')
replace('  function projectArtworkAction(line){', '  function projectArtworkAction(line,index){')
replace("    if(multiPanelArtwork(p))return '<span class=\"badge blue\">Upload concept at checkout</span><button class=\"btn light\" data-action=\"design-quote\">Request design help</button>';", "    if(multiPanelArtwork(p))return `${windowUploads.button(project[index])}<button class=\"btn light\" data-action=\"design-quote\">Request design help</button>`;")
replace('${projectArtworkAction(line)}', '${projectArtworkAction(line,i)}')
replace("    $$('[data-project-quantity], [data-project-size]').forEach", "    await windowUploads.refresh();\n    $$('[data-project-quantity], [data-project-size]').forEach")
replace('    const files=[],imageUploads=uploadedFiles.filter', '    const files=await windowUploads.filesFor(project),imageUploads=uploadedFiles.filter')
replace('  Object.assign(actions,{', '  Object.assign(actions,windowUploads.actions,{')
replace("    'project-checkout':async()=>{await quoteProject();state.projectCheckout=true;orderModal();},", "    'project-checkout':async()=>{await quoteProject();state.projectCheckout=true;orderModal();await windowUploads.checkoutHint(project);},")
path.write_text(text)

for filename, old, new in [
    ('app/static/app.js', "./shop.js?v=20260924-2", "./shop.js?v=20260924-window-upload"),
    ('app/static/app.js', 'One design per order. Wraps, installation and sizes outside the listed limits need a custom quote.', "${cfg.supports_multiple_dimensions?'Multiple window designs are welcome. Attach separate pane files or a multi-page PDF.':'One design per order.'} Wraps, installation and sizes outside the listed limits need a custom quote."),
    ('app/static/index.html', '/static/app.js?v=20260924-2', '/static/app.js?v=20260924-window-upload')
]:
    p = Path(filename)
    body = p.read_text()
    if body.count(old) != 1:
        raise RuntimeError(f'Unexpected source state: {filename}')
    p.write_text(body.replace(old, new, 1))
print('Applied guarded window-artwork integration and browser cache refresh.')
