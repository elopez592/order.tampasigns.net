"""Expose the existing wrap classification; do not change products or pricing."""
from pathlib import Path
path = Path('app/main.py')
body = path.read_text(encoding='utf-8')
for old, new in [
    ("'default_width','default_height','min_width','min_height','instant','supports_installation',", "'default_width','default_height','min_width','min_height','instant','is_wrap','supports_installation',"),
    ("defaults = {'supports_installation': False, 'supports_multiple_dimensions': False,", "defaults = {'is_wrap': False, 'supports_installation': False, 'supports_multiple_dimensions': False,")
]:
    if body.count(old) != 1:
        raise RuntimeError('Unexpected public catalog source: ' + old)
    body = body.replace(old, new, 1)
path.write_text(body, encoding='utf-8')
print('Public catalog exposes existing is_wrap classification; no rates or eligibility changed.')
