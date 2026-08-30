from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_policy() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parent.parent / 'policy.yaml'
    with policy_path.open('r', encoding='utf-8') as handle:
        data = yaml.safe_load(handle) or {}
    return data
