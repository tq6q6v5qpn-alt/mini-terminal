# analyzer.py
from typing import Dict, Any


def regime(m: Dict[str, Any]) -> str:
    """
    아주 단순한 레짐 분류:
    - BTC 5-step 수익률이 플러스고, 변동성(σ)이 낮으면 Risk-On
    - BTC 5-step 수익률이 마이너스고, 변동성이 높으면 Risk-Off
    - 그 외 Neutral
    """
    r5 = float(m.get("BTC_R5", 0.0) or 0.0)
    vol = float(m.get("VOL", 0.0) or 0.0)

    if r5 > 0.3 and vol < 1.5:
        return "Risk-On"
    if r5 < -0.3 and vol > 1.5:
        return "Risk-Off"
    return "Neutral"
