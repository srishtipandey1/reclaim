from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_eval import build_design_cases, build_eval_cases, write_json


def main() -> None:
    for directory, cases in (
        (ROOT / 'eval' / 'design_set', build_design_cases()),
        (ROOT / 'eval' / 'eval_set', build_eval_cases()),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        for case in cases:
            write_json(directory / f"{case['id']}.json", case)


if __name__ == '__main__':
    main()
