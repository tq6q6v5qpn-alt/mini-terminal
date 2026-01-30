# features.py
from typing import Any, Dict, Optional, Tuple
from state import load_state, save_state


def _get_bucket(state: Dict[str, Any], name: str) -> Dict[str, Any]:
    if name not in state or not isinstance(state.get(name), dict):
        state[name] = {}
    return state[name]


def slope_acc(key: str, value: float) -> Tuple[float, float]:
    """
    d1 = 현재 - 이전
    d2 = d1 - 이전 d1
    상태는 /tmp/canary_state.json 에 저장
    """
    state = load_state()
    bucket = _get_bucket(state, "slope_acc")

    prev = bucket.get(key)
    prev_d1 = bucket.get(f"{key}_d1")

    if prev is None:
        d1, d2 = 0.0, 0.0
    else:
        d1 = float(value) - float(prev)
        if prev_d1 is None:
            d2 = 0.0
        else:
            d2 = float(d1) - float(prev_d1)

    bucket[key] = float(value)
    bucket[f"{key}_d1"] = float(d1)

    save_state(state)
    return float(d1), float(d2)


def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None
