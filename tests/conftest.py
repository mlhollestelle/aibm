"""Pytest configuration shared across all test modules.

Adds workflow/scripts to sys.path so tests can import helper
functions from the pipeline scripts directly.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "workflow" / "scripts"))
