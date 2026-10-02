"""Trusted, bundled storefront media for an isolated company."""
import json
import re
from pathlib import Path


def public_media(app):
    if getattr(app.state, 'platform_enabled', True):
        return {}
    slug = app.state.database.parent.name
    if not re.fullmatch(r'[a-z][a-z0-9-]{2,39}', slug):
        return {}
    manifest = Path(__file__).parent / 'company_setups' / slug / 'media.json'
    if not manifest.is_file():
        return {}
    data = json.loads(manifest.read_text())
    return {key: data.get(key, {} if key == 'products' else [] if key == 'projects' else '')
            for key in ('products', 'projects', 'instagram', 'default_product')}
