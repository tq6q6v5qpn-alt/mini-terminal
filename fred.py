# fred.py
import os
import requests
from typing import Dict, Optional, Tuple

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ===== A: Policy Corridor =====
SER_SOFR = "SOFR"
SER_EFFR = "EFFR"
SER_IORB = "IORB"

# ===== B: RRP / TGA / Reserves =====
SER_ONRRP = "ONRRP"
SER_TGA = "WTREGEN"
SER_RESERVES = "RESBALNS"

# ===== C: Repo / Collateral =====
SER_BGCR = "BGCR"  # TGCR 안 씀

# ===== D: UST Yield Curve =====
SER_DGS2 = "DGS2"
SER_DGS10 = "DGS10"

# ===== E: USD Strength =====
SER_DTWEX = "DTWEXBGS"


def _latest(series_id: str) -> Optional[float]:
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return None

    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
    }

    try:
        r = requests.get(FRED_BASE, params=params, timeout=15)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        if not obs:
            return None
        v = obs[0].get("value")
        if v in (None, ".", ""):
            return None
        return float(v)
    except Exception:
        return None


def liquidity_snapshot() -> Dict[str, Optional[float]]:
    return {
        "SOFR": _latest(SER_SOFR),
        "EFFR": _latest(SER_EFFR),
        "IORB": _latest(SER_IORB),
        "ONRRP": _latest(SER_ONRRP),
        "TGA": _latest(SER_TGA),
        "RESERVES": _latest(SER_RESERVES),
        "BGCR": _latest(SER_BGCR),
        "DGS2": _latest(SER_DGS2),
        "DGS10": _latest(SER_DGS10),
        "DTWEX": _latest(SER_DTWEX),
    }


def liquidity_canary() -> Tuple[str, str, Dict[str, Optional[float]]]:
    """
    반환값(절대 3개 고정)
      1) trigger_line (str)
      2) conclusion   (str)
      3) liq          (dict)
    """
    liq = liquidity_snapshot()

    sofr = liq.get("SOFR")
    effr = liq.get("EFFR")
    iorb = liq.get("IORB")

    onrrp = liq.get("ONRRP")
    tga = liq.get("TGA")
    reserves = liq.get("RESERVES")

    bgcr = liq.get("BGCR")
    dgs2 = liq.get("DGS2")
    dgs10 = liq.get("DGS10")
    dtwex = liq.get("DTWEX")

    # -------- A) Policy Corridor --------
    A = "A: None"
    concA = "A: 데이터 없음"
    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr

        if abs(spread_sofr_effr) >= 0.10:
            A = f"A: SOFR-EFFR {spread_sofr_effr:+.2f}% (코리더 이탈)"
            concA = "A: 스프레드 확대(현금/담보 압력 신호 가능)"
        elif spread_iorb_effr < 0.02:
            A = f"A: EFFR≈IORB (IORB-EFFR {spread_iorb_effr:+.2f}%)"
            concA = "A: 코리더 상단 압박(규제/정책 톤 변화 후보)"
        else:
            A = "A: 코리더 정상"
            concA = "A: 정책 코리더 정상"

    # -------- B) RRP / TGA / Reserves --------
    B = "B: None"
    concB = "B: 데이터 없음"
    if (onrrp is not None) and (tga is not None) and (reserves is not None):
        B = f"B: ONRRP={onrrp:,.0f} | TGA={tga:,.0f} | RES={reserves:,.0f}"
        concB = "B: 레벨 갱신(변화/가속은 main에서 추적)"

    # -------- C) Repo spread --------
    C = "C: None"
    concC = "C: 데이터 없음"
    if (bgcr is not None) and (sofr is not None):
        repo_spread = bgcr - sofr
        if abs(repo_spread) >= 0.10:
            C = f"C: BGCR-SOFR {repo_spread:+.2f}% (레포 긴장)"
            concC = "C: 담보/현금 불균형 확대"
        else:
            C = f"C: BGCR-SOFR {repo_spread:+.2f}%"
            concC = "C: 레포 스프레드 안정"

    # -------- D/E (레벨만 표시, slope/acc는 main에서) --------
    D = "D: None"
    if (dgs2 is not None) and (dgs10 is not None):
        curve = dgs10 - dgs2
        D = f"D: UST 2Y={dgs2:.2f}% | 10Y={dgs10:.2f}% | (10-2)={curve:+.2f}%"

    E = "E: None"
    if dtwex is not None:
        E = f"E: USD(DTWEX)={dtwex:.2f}"

    trigger_line = f"{A} | {B} | {C} | {D} | {E}"
    conclusion = f"{concA} / {concB} / {concC}"

    return trigger_line, conclusion, liq
