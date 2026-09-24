import shutil
import subprocess
from pathlib import Path
import pytest


def test_wrap_artwork_lifecycle():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend lifecycle tests')
    subprocess.run([node, 'tests/wrap_upload.test.mjs'], cwd=Path(__file__).resolve().parents[1], check=True, timeout=30)
