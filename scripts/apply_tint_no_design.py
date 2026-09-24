"""Remove design-only prompts from no-artwork products without changing rates."""
from pathlib import Path
import re

path = Path('app/static/app.js')
text = path.read_text(encoding='utf-8')

def replace(old, new):
    global text
    if text.count(old) != 1:
        raise RuntimeError(f'Expected one safe anchor: {old[:100]}')
    text = text.replace(old, new, 1)

sections = re.findall(r'<section class="custom-quote-cta"><div><div class="eyebrow">DESIGN HELP</div>.*?</section>', text, flags=re.S)
if len(sections) != 1:
    raise RuntimeError('Expected one shared design-help section.')
replace(sections[0], "${cfg.artwork_upload_disabled?'':`" + sections[0] + "`}")
replace('<span class="preview-label">Your artwork. Your size. Your style.</span>', '<span class="preview-label">${cfg.artwork_upload_disabled?\'Window tinting. Film selection. Installation.\':\'Your artwork. Your size. Your style.\'}</span>')
old_hint = "${cfg.is_wrap?'Attach wrap artwork, logos or reference files using Upload Design.':cfg.supports_multiple_dimensions?'Multiple window designs are welcome. Attach separate pane files or a multi-page PDF.':'One design per order.'} Wraps, installation and sizes outside the listed limits need a custom quote."
replace(old_hint, "${cfg.artwork_upload_disabled?'Choose your tinting options and submit your measurements. Film selection and installation are confirmed after review.':`" + old_hint + "`}")
replace('disabled>Continue to artwork ${icon(\'arrow\')}</button>', 'disabled>Add to project ${icon(\'arrow\')}</button>')
replace('${esc(state.catalog.shop.quote_note)}', "${esc(cfg.artwork_upload_disabled?'Tinting estimates are reviewed for glass coverage, film choice and installation before scheduling.':state.catalog.shop.quote_note)}")
replace('<span>Review your proof before production.</span>', "<span>${cfg.artwork_upload_disabled?'Confirm film and installation details before scheduling.':'Review your proof before production.'}</span>")
replace('<span>Secure checkout for eligible print orders.</span>', "<span>${cfg.artwork_upload_disabled?'Receive a reviewed tinting quote.':'Secure checkout for eligible print orders.'}</span>")
replace("if(serviceSelect&&!serviceSelect.querySelector('option[value=\"design_quote\"]'))", "if(serviceSelect&&!cfg.artwork_upload_disabled&&!serviceSelect.querySelector('option[value=\"design_quote\"]'))")
replace("${state.catalog.notifications?.enabled?'We will email you when your project is received, a proof is ready, production begins, and your order is finished.':'Your private project link opens next. Save it to return to your proof and updates.'}", "${acceptsArtwork?(state.catalog.notifications?.enabled?'We will email you when your project is received, a proof is ready, production begins, and your order is finished.':'Your private project link opens next. Save it to return to your proof and updates.'):(state.catalog.notifications?.enabled?'We will email updates about your tinting request.':'Your private project link opens next. Save it to return to your quote and updates.')}")
index = Path('app/static/index.html')
html = index.read_text(encoding='utf-8')
old_version = '/static/app.js?v=20260924-wrap-artwork'
if html.count(old_version) != 1:
    raise RuntimeError('Unexpected application cache version.')
path.write_text(text, encoding='utf-8')
index.write_text(html.replace(old_version, '/static/app.js?v=20260924-tint-no-design', 1), encoding='utf-8')
print('Removed shared design help and artwork/proof prompts for tinting; preserved other products and all pricing.')
