# state.py
import json
import os
from typing import Any, Dict

STATE_PATH = os.getenv("STATE_PATH", "/tmp/canary_state.json")


def load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
    except Exception:
        # 저장 실패해도 cron 죽이면 안 됨
        pass
