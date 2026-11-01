import sys
from pathlib import Path

# Allow `python -m unittest` from the repository root without installing the package.
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
