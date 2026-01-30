# fred.py
import os
import requests
from datetime import datetime, timezone

from state import get_num, set_num  # ✅ Δ/ΔΔ 저장용

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
SER_BGCR = "BGCR"   # ✅ TGCR 안 씀


def _now():
    return datetime.now(timezone.utc).isoformat()


def slope_acc(key: str, v: float):
    """
    state에 v 저장하면서
    d1 = Δ(기울기), d2 = ΔΔ(가속) 계산
    """
    prev = get_num(key)
    prev_d = get_num(key + "_d")

    d1 = (v - prev) if (prev is not None) else 0.0
    d2 = (d1 - prev_d) if (prev_d is not None) else 0.0

    ts = _now()
    set_num(key, v, ts)
    set_num(key + "_d", d1, ts)
    return d1, d2


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
        return None


def liquidity_snapshot():
    """
    raw 레벨만
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
    return: posL, negL, conclL, liq
    - posL/negL: "A: ... | B: ... | C: ..." 형식
    - conclL: 1줄 결론 (A/B/C 요약)
    - liq: raw dict
    """
    liq = liquidity_snapshot()

    sofr = liq.get("SOFR")
    effr = liq.get("EFFR")
    iorb = liq.get("IORB")

    onrrp = liq.get("ONRRP")
    tga = liq.get("TGA")
    reserves = liq.get("RESERVES")

    bgcr = liq.get("BGCR")

    # ---------- Δ/ΔΔ 계산(값이 있을 때만) ----------
    # 단위 주의:
    # ONRRP/TGA/RESERVES 는 보통 "Millions of Dollars"라서 10,000 = $10B
    d_onrrp = d2_onrrp = None
    d_tga = d2_tga = None
    d_res = d2_res = None
    d_spread = d2_spread = None

    if onrrp is not None:
        d_onrrp, d2_onrrp = slope_acc("FRED_ONRRP", onrrp)
    if tga is not None:
        d_tga, d2_tga = slope_acc("FRED_TGA", tga)
    if reserves is not None:
        d_res, d2_res = slope_acc("FRED_RESERVES", reserves)

    spread_bgcr_sofr = None
    if (bgcr is not None) and (sofr is not None):
        spread_bgcr_sofr = bgcr - sofr
        d_spread, d2_spread = slope_acc("FRED_SPREAD_BGCR_SOFR", spread_bgcr_sofr)

    # =========================================================
    # A) Policy Corridor (레벨 중심 + 약한 트리거)
    # =========================================================
    A_pos = "A: None"
    A_neg = "A: None"
    concA = "A: 데이터 없음"

    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr  # +면 IORB가 EFFR 위

        # Tightening/Stress 쪽(neg): SOFR-EFFR 급확대(현장 조달 압박)
        if abs(spread_sofr_effr) >= 0.10:
            A_neg = f"A: SOFR-EFFR {spread_sofr_effr:+.2f}% (코리더 이탈/압박)"
            concA = "A: 코리더 스프레드 확대(현장 자금 압박)"
        # Easing 쪽(pos): 스프레드가 음(-)으로 크게(현장금리 완화) 가는 케이스는 드묾 → 보수적으로 둠
        elif spread_sofr_effr <= -0.05:
            A_pos = f"A: SOFR<EFFR {spread_sofr_effr:+.2f}% (완화/왜곡)"
            concA = "A: 현장금리 완화/왜곡"
        # Neutral but watch: EFFR이 IORB에 바짝(코리더 상단 밀착)
        elif spread_iorb_effr < 0.02:
            A_neg = f"A: EFFR~IORB (IORB-EFFR {spread_iorb_effr:+.2f}%)"
            concA = "A: 코리더 상단 압박(정책/규제 톤 변화 후보)"
        else:
            concA = "A: 정책 코리더 정상(압력 약함)"

    # =========================================================
    # B) ONRRP / TGA / RESERVES (Δ/ΔΔ 중심)
    # =========================================================
    B_pos = "B: None"
    B_neg = "B: None"
    concB = "B: 데이터 없음"

    # 임계치 (단위: Millions of $)
    # 25,000 = $25B / 50,000 = $50B
    BIG = 50_000
    MID = 25_000

    if (onrrp is not None) and (tga is not None) and (reserves is not None) and \
       (d_onrrp is not None) and (d_tga is not None) and (d_res is not None):

        # 해석:
        # - ONRRP 감소(자금이 시장으로) + RES 증가 => 완화(positive)
        # - TGA 증가(재무부가 유동성 흡수) + RES 감소 => 긴축(negative)
        # - ΔΔ(가속)이 크면 “급변”
        pos_hits = []
        neg_hits = []

        # ONRRP drain → easing 후보
        if d_onrrp <= -MID:
            pos_hits.append(f"ONRRP↓ {d_onrrp/1000:+.1f}B")
        if d2_onrrp is not None and abs(d2_onrrp) >= MID:
            # 가속 자체는 방향보다 "급변" 강조
            if d2_onrrp < 0:
                pos_hits.append(f"ONRRPΔΔ↓ {d2_onrrp/1000:+.1f}B")
            else:
                neg_hits.append(f"ONRRPΔΔ↑ {d2_onrrp/1000:+.1f}B")

        # TGA build → tightening 후보
        if d_tga >= MID:
            neg_hits.append(f"TGA↑ {d_tga/1000:+.1f}B")
        if d2_tga is not None and abs(d2_tga) >= MID:
            if d2_tga > 0:
                neg_hits.append(f"TGAΔΔ↑ {d2_tga/1000:+.1f}B")
            else:
                pos_hits.append(f"TGAΔΔ↓ {d2_tga/1000:+.1f}B")

        # Reserves move
        if d_res >= MID:
            pos_hits.append(f"RES↑ {d_res/1000:+.1f}B")
        if d_res <= -MID:
            neg_hits.append(f"RES↓ {d_res/1000:+.1f}B")
        if d2_res is not None and abs(d2_res) >= MID:
            if d2_res > 0:
                pos_hits.append(f"RESΔΔ↑ {d2_res/1000:+.1f}B")
            else:
                neg_hits.append(f"RESΔΔ↓ {d2_res/1000:+.1f}B")

        # “브리지” 패턴: 더 강한 신호
        if (d_onrrp <= -MID) and (d_res >= MID):
            pos_hits.append("BRIDGE: RRP→RES(완화)")
        if (d_tga >= MID) and (d_res <= -MID):
            neg_hits.append("BRIDGE: TGA↑+RES↓(긴축)")

        if pos_hits:
            B_pos = "B: " + ", ".join(pos_hits)
        if neg_hits:
            B_neg = "B: " + ", ".join(neg_hits)

        if ("BRIDGE: RRP→RES(완화)" in (B_pos or "")) or (d_onrrp <= -BIG) or (d_res >= BIG):
            concB = "B: 단기 유동성 완화(흡수통→준비금 브리지/급변)"
        elif ("BRIDGE: TGA↑+RES↓(긴축)" in (B_neg or "")) or (d_tga >= BIG) or (d_res <= -BIG):
            concB = "B: 단기 유동성 긴축(재무부 흡수/준비금 감소 급변)"
        else:
            concB = "B: 레벨 갱신(급변 없음)"

    # =========================================================
    # C) BGCR – SOFR (스프레드 + Δ/ΔΔ)
    # =========================================================
    C_pos = "C: None"
    C_neg = "C: None"
    concC = "C: 데이터 없음"

    # bp 기준: 0.01% = 1bp, 0.10% = 10bp
    if (spread_bgcr_sofr is not None) and (d_spread is not None) and (d2_spread is not None):
        repo_spread = spread_bgcr_sofr

        # 레벨 기반 스트레스(neg)
        if abs(repo_spread) >= 0.10:
            C_neg = f"C: BGCR-SOFR {repo_spread:+.2f}% (레포/담보 타이트)"
            concC = "C: 레포 스프레드 확대(담보/현금 불균형)"
        else:
            # “급변”은 Δ/ΔΔ로 잡기: 5bp(0.05%) 이상이면 의미있는 점프
            jump = 0.05
            if d_spread >= jump or d2_spread >= jump:
                C_neg = f"C: 스프레드 급등 Δ{d_spread:+.2f}% ΔΔ{d2_spread:+.2f}%"
                concC = "C: 레포 스프레드 급등(턴엔드/담보 타이트 후보)"
            elif d_spread <= -jump or d2_spread <= -jump:
                C_pos = f"C: 스프레드 급락 Δ{d_spread:+.2f}% ΔΔ{d2_spread:+.2f}%"
                concC = "C: 레포 스프레드 완화(현장 타이트 해소)"
            else:
                concC = "C: 레포 스프레드 안정"

    # =========================================================
    # 출력 포맷 (네 main.py가 그대로 쓰게)
    # =========================================================
    posL = f"{A_pos} | {B_pos} | {C_pos}"
    negL = f"{A_neg} | {B_neg} | {C_neg}"

    conclL = f"{concA} / {concB} / {concC}"

    return posL, negL, conclL, liq
