#!/usr/bin/env python3
"""Print registry Skill entries as JSON for PowerShell installation."""
import json
import sys
from pathlib import Path

import yaml


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    data = yaml.safe_load((root / "shared" / "skill-registry.yaml").read_text(encoding="utf-8"))
    print(json.dumps(data["skills"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
