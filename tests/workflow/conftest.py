"""Add workflow/scripts to sys.path for workflow tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "workflow" / "scripts"))
