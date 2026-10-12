"""Run the node tests for the assistant-context helpers and the shipping app.js."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_copilot_context_node_tests_pass():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node required for the UI context tests")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, "--test", "tests/copilot-context.test.mjs"], cwd=root, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr