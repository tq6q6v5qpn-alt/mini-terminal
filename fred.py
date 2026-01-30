# fred.py
import os
import requests

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# ===== A: Policy Corridor =====
SER_SOFR = "SOFR"       # Secured Overnight Financing Rate
SER_EFFR = "EFFR"       # Effective Federal Funds Rate
SER_IORB = "IORB"       # Interest on Reserve Balances (FRED에 존재)

# ===== B: RRP / TGA / Reserves =====
SER_ONRRP = "ONRRP"     # Overnight Reverse Repurchase Agreements: Treasury Securities Sold by the Fed in the Temporary Open Market Operations
SER_TGA = "WTREGEN"     # Treasury General Account (TGA)
SER_RESERVES = "RESBALNS"  # Reserve Balances with Federal Reserve Banks

# ===== C: Repo / Collateral =====
SER_BGCR = "BGCR"       # Broad General Collateral Rate (TGCR은 사용 안 함)

def _latest(series_id: str):
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        raise RuntimeError("Missing env var: FRED_API_KEY")

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
        # 여기서 죽으면 cronjob이 죽어버리니까, None으로 반환해서 상위에서 처리
        return None

def liquidity_snapshot():
    """
    raw 레벨 값만 가져오는 스냅샷(dict)
    """
    return {
        "SOFR": _latest(SER_SOFR),
        "EFFR": _latest(SER_EFFR),
        "IORB": _latest(SER_IORB),
        "ONRRP": _latest(SER_ONRRP),
        "TGA": _latest(SER_TGA),
        "RESERVES": _latest(SER_RESERVES),
        "BGCR": _latest(SER_BGCR),
    }

def liquidity_canary():
    """
    A/B/C 트리거 문자열 + 결론 1줄 + (옵션)liq dict 반환
    - TGCR 없음
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
    # 코리더 압력(단순): EFFR이 IORB에 붙거나, SOFR-EFFR 벌어짐
    # None이면 "None"
    A = "A: None"
    concA = "A: 데이터 없음"
    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr

        # 임계값은 보수적으로 시작(너가 원하는 “기울기/가속”은 main.py에서 Δ/ΔΔ로 강화)
        if abs(spread_sofr_effr) >= 0.10:
            A = f"A: SOFR-EFFR 스프레드 {spread_sofr_effr:+.2f}% (코리더 이탈 징후)"
            concA = "A: 코리더 스프레드 확대(자금 압력/완화 신호 가능)"
        elif spread_iorb_effr < 0.02:
            A = f"A: EFFR가 IORB에 바짝( IORB-EFFR {spread_iorb_effr:+.2f}% )"
            concA = "A: 코리더 상단 압박(정책/규제 톤 변화 감지 후보)"
        else:
            A = "A: Policy corridor 정상 범위"
            concA = "A: 정책 코리더 정상(압력 징후 약함)"

    # -------- B) RRP / TGA / Reserves --------
    # 방향성이 핵심이라 “레벨”은 결론에만
    B = "B: None"
    concB = "B: 데이터 없음"
    if (onrrp is not None) and (tga is not None) and (reserves is not None):
        B = f"B: ONRRP={onrrp:,.0f} | TGA={tga:,.0f} | RES={reserves:,.0f}"
        concB = "B: 레벨 갱신(Δ/ΔΔ는 다음 라운드에서 알람 기준으로 씀)"

    # -------- C) Repo spread / Turn-end spikes --------
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

    # 트리거 문자열(한 줄)
    trigger_line = f"{A} | {B} | {C}"
    conclusion = f"{concA} / {concB} / {concC}"

    return trigger_line, conclusion, liq
