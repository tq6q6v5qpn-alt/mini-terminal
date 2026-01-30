# fred.py
import os
import requests

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
SER_BGCR = "BGCR"   # TGCR 안 씀

# ===== D: UST Yield Curve =====
SER_DGS2 = "DGS2"      # US 2Y Treasury
SER_DGS10 = "DGS10"    # US 10Y Treasury

# ===== E: USD Strength =====
SER_DTWEX = "DTWEXBGS" # Broad USD Index


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


def liquidity_snapshot():
    """raw 레벨 값 스냅샷(dict)"""
    return {
        # A
        "SOFR": _latest(SER_SOFR),
        "EFFR": _latest(SER_EFFR),
        "IORB": _latest(SER_IORB),

        # B
        "ONRRP": _latest(SER_ONRRP),
        "TGA": _latest(SER_TGA),
        "RESERVES": _latest(SER_RESERVES),

        # C
        "BGCR": _latest(SER_BGCR),

        # D
        "DGS2": _latest(SER_DGS2),
        "DGS10": _latest(SER_DGS10),

        # E
        "DTWEX": _latest(SER_DTWEX),
    }


def liquidity_canary():
    """
    반환값(절대 3개 고정):
      1) trigger_line (str) : "A: ... | B: ... | C: ..."
      2) conclusion   (str) : "A: ... / B: ... / C: ..."
      3) liq          (dict): raw 레벨 스냅샷 (+ D/E 레벨도 포함)
    """
    liq = liquidity_snapshot()

    sofr = liq.get("SOFR")
    effr = liq.get("EFFR")
    iorb = liq.get("IORB")

    onrrp = liq.get("ONRRP")
    tga = liq.get("TGA")
    reserves = liq.get("RESERVES")

    bgcr = liq.get("BGCR")

    # -------- A) Policy Corridor --------
    A = "A: None"
    concA = "A: 데이터 없음"
    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr

        if abs(spread_sofr_effr) >= 0.10:
            A = f"A: SOFR-EFFR {spread_sofr_effr:+.2f}% (코리더 이탈 징후)"
            concA = "A: 코리더 스프레드 확대(자금 압력/완화 신호 가능)"
        elif spread_iorb_effr < 0.02:
            A = f"A: EFFR가 IORB에 바짝 (IORB-EFFR {spread_iorb_effr:+.2f}%)"
            concA = "A: 코리더 상단 압박(정책/규제 톤 변화 감지 후보)"
        else:
            A = "A: Policy corridor 정상 범위"
            concA = "A: 정책 코리더 정상(압력 징후 약함)"

    # -------- B) RRP / TGA / Reserves --------
    B = "B: None"
    concB = "B: 데이터 없음"
    if (onrrp is not None) and (tga is not None) and (reserves is not None):
        B = f"B: ONRRP={onrrp:,.0f} | TGA={tga:,.0f} | RES={reserves:,.0f}"
        concB = "B: 레벨 갱신(Δ/ΔΔ는 main에서 변화로 감시)"

    # -------- C) Repo spread --------
    C = "C: None"
    concC = "C: 데이터 없음"
    if (bgcr is not None) and (sofr is not None):
        repo_spread = bgcr - sofr
        if abs(repo_spread) >= 0.10:
            C = f"C: BGCR-SOFR {repo_spread:+.2f}% (담보/현금 타이트 징후)"
            concC = "C: 레포 스프레드 확대(현장 담보/현금 불균형)"
        else:
            C = f"C: BGCR-SOFR {repo_spread:+.2f}%"
            concC = "C: 레포 스프레드 안정"

    trigger_line = f"{A} | {B} | {C}"
    conclusion = f"{concA} / {concB} / {concC}"
    return trigger_line, conclusion, liq
