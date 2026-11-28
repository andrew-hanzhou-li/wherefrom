"""Runs the extension's JavaScript tests (tests/extension/*.test.js) with
Node, so they're part of every pytest run. Skipped without Node, except on
CI, where a missing Node is a failure."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent


def test_extension_logic_with_node():
    node = shutil.which("node")
    if not node:
        if os.environ.get("CI"):
            pytest.fail("Node is needed for the extension's tests")
        pytest.skip("Node isn't installed")
    files = sorted(str(p) for p in (HERE / "extension").glob("*.test.js"))   # node only expands globs itself from v21
    assert files
    result = subprocess.run([node, "--test", *files], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
