import shutil
import subprocess
from pathlib import Path
import pytest


def test_canva_plus_file_upload_lifecycle():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js is required for frontend lifecycle tests')
    subprocess.run([node, 'tests/canva_upload.test.mjs'], cwd=Path(__file__).resolve().parents[1], check=True, timeout=30)
