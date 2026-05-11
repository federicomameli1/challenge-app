"""
Root pytest configuration.
Ensures project root is on sys.path for all agentN/ and brain/ packages.
"""

import sys as _sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[0]
if _ROOT not in _sys.path:
    _sys.path.insert(0, str(_ROOT))
elif _sys.path[0] != str(_ROOT):
    # Move project root to index 0 so 'import agent6' resolves here.
    idx = _sys.path.index(str(_ROOT))
    _sys.path.pop(idx)
    _sys.path.insert(0, str(_ROOT))

# Import a top-level agent6 module so it is cached in sys.modules.
# This prevents pytest's test-discovery path from shadowing the real package.
import agents.agent6.models  # noqa: F401
