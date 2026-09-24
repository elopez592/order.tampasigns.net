"""Exercise the customer window-artwork lifecycle alongside Python regressions."""
import shutil
import subprocess
from pathlib import Path
import pytest


def test_window_artwork_lifecycle():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend lifecycle tests')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([node, 'tests/window_upload.test.mjs'], cwd=root, check=True, timeout=30)
