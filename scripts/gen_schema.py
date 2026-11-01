"""Regenerate src/vicode/data/vicode.schema.json from the configuration spec."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vicode import config  # noqa: E402

target = ROOT / "src" / "vicode" / "data" / "vicode.schema.json"
target.write_text(config.schema_json_text(), encoding="utf-8", newline="\n")
print(f"wrote {target}")
