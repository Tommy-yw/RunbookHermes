from __future__ import annotations

import json
from .smoke import run_smoke

if __name__ == "__main__":
    print(json.dumps(run_smoke(), ensure_ascii=False, indent=2))
