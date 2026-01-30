# fred.py
import os
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ===== A: Policy Corridor =====
SER_SOFR = "SOFR"
SER_EFFR = "EFFR"
SER_IORB = "IORB"

# ===== B: Liquidity =====
SER_ONRRP = "ONRRP"
SER_TGA = "WTREGEN"
SER_RESERVES = "RESBALNS"

# ===== C: Repo =====
SER_BGCR = "BGCR"

# ===== D: UST Yield =====
SER_DGS2 = "DGS2"
SER_DGS10 = "DGS10"

# ===== E: USD =====
SER_DTWEX = "DTWEXBGS"


def _latest(series_id: str):
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
        r = requests.get(FRED_BASE, params=params, timeout=10)
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


def liquidity_canary():
    """
    항상 3개만 반환 (절대 변경 금지)
    """
    liq = {
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

    # ----- A -----
    A, concA = "A: None", "A: 데이터 없음"
    if liq["SOFR"] and liq["EFFR"] and liq["IORB"]:
        if liq["IORB"] - liq["EFFR"] < 0.02:
            A = f"A: EFFR≈IORB (+{liq['IORB']-liq['EFFR']:.2f}%)"
            concA = "A: 정책 코리더 상단 압박"
        else:
            A = "A: Policy corridor 정상"
            concA = "A: 정책 안정"

    # ----- B -----
    B, concB = "B: None", "B: 데이터 없음"
    if liq["ONRRP"] and liq["TGA"] and liq["RESERVES"]:
        B = f"B: RRP={liq['ONRRP']:.0f} | TGA={liq['TGA']:.0f}"
        concB = "B: 유동성 레벨 관찰"

    # ----- C -----
    C, concC = "C: None", "C: 데이터 없음"
    if liq["BGCR"] and liq["SOFR"]:
        spread = liq["BGCR"] - liq["SOFR"]
        C = f"C: Repo spread {spread:+.2f}%"
        concC = "C: 담보/현금 상태"

    trigger = f"{A} | {B} | {C}"
    conclusion = f"{concA} / {concB} / {concC}"

    return trigger, conclusion, liq
