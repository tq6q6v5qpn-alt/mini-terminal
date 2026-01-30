import os
import requests
from datetime import datetime, timezone, timedelta

from state import get_num, set_num

KST = timezone(timedelta(hours=9))
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def latest(series_id: str):
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

    r = requests.get(FRED_BASE, params=params, timeout=10)
    r.raise_for_status()
    obs = r.json().get("observations", [])
    if not obs:
        return None

    v = obs[0].get("value")
    if v in (None, ".", ""):
        return None

    try:
        return float(v)
    except:
        return None


def slope_acc(key: str, v: float):
    """
    state에 (레벨, 1차 변화, 2차 변화)를 저장/계산
    d1 = Δ(기울기), d2 = ΔΔ(가속)
    """
    prev = get_num(key)
    prev_d1 = get_num(key + "_d1")

    d1 = (v - prev) if (prev is not None) else 0.0
    d2 = (d1 - prev_d1) if (prev_d1 is not None) else 0.0

    now = datetime.now(KST).isoformat()
    set_num(key, v, now)
    set_num(key + "_d1", d1, now)
    return d1, d2


# -------------------------
# A) Policy Corridor (SOFR/EFFR/IORB) 이탈/압력
# -------------------------
def corridor_signals():
    # FRED series ids (가끔 바뀌거나 다른 이름일 수 있음)
    # 안 나오면 logs에서 series_id 에러 확인 후 여기만 고치면 됨.
    sofr = latest("SOFR")
    effr = latest("EFFR")
    iorb = latest("IORB")  # 만약 None이면 FRED에서 IORB series id가 다른 것

    if (sofr is None) or (effr is None) or (iorb is None):
        return (
            "A(Policy Corridor): None (missing series)",
            "A(Policy Corridor): None (missing series)",
            "A: FRED series missing (SOFR/EFFR/IORB 확인 필요)",
            {}
        )

    # spreads (단위: %)
    s_sofr_effr = sofr - effr
    s_sofr_iorb = sofr - iorb
    s_effr_iorb = effr - iorb

    # Δ/ΔΔ (기울기/가속) — 네 우선순위 3종 세트
    d1_a1, d2_a1 = slope_acc("A_SOFR_EFFR", s_sofr_effr)
    d1_a2, d2_a2 = slope_acc("A_SOFR_IORB", s_sofr_iorb)
    d1_a3, d2_a3 = slope_acc("A_EFFR_IORB", s_effr_iorb)

    # 임계치 (bps 기준으로 보기 편하게)
    # 0.01% = 1bp
    TH_WIDE = 0.05   # 5bp
    TH_SHOCK = 0.10  # 10bp

    # “압력” 정의(예시):
    # - SOFR가 EFFR/IORB 대비 급격히 위로 벌어지는 방향 + 가속(ΔΔ>0)
    wide_1 = (s_sofr_effr >= TH_WIDE and d1_a1 > 0 and d2_a1 > 0)
    wide_2 = (s_sofr_iorb >= TH_WIDE and d1_a2 > 0 and d2_a2 > 0)
    shock  = (s_sofr_effr >= TH_SHOCK) or (s_sofr_iorb >= TH_SHOCK)

    if shock:
        neg = (
            f"A⚠️ Corridor Stress: SOFR premium spike "
            f"(SOFR-EFFR={s_sofr_effr*100:.1f}bp, SOFR-IORB={s_sofr_iorb*100:.1f}bp)"
        )
        pos = "A: None"
        concl = "A: 코리더 이탈(현장 자금조달 압력) 신호가 강해짐"
    elif wide_1 or wide_2:
        neg = (
            f"A⚠️ Corridor Widening: SOFR premium rising "
            f"(Δ/ΔΔ +) | (SOFR-EFFR={s_sofr_effr*100:.1f}bp, SOFR-IORB={s_sofr_iorb*100:.1f}bp)"
        )
        pos = "A: None"
        concl = "A: 코리더가 벌어지는 방향(압력 증가) — 지속 여부 관찰"
    else:
        pos = (
            f"A✅ Corridor OK: spreads stable "
            f"(SOFR-EFFR={s_sofr_effr*100:.1f}bp, SOFR-IORB={s_sofr_iorb*100:.1f}bp)"
        )
        neg = "A: None"
        concl = "A: 정책 코리더 정상 범위(압력 징후 약함)"

    snap = {
        "SOFR": sofr,
        "EFFR": effr,
        "IORB": iorb,
        "A_SOFR_EFFR_bp": s_sofr_effr * 100,  # bp
        "A_SOFR_IORB_bp": s_sofr_iorb * 100,
        "A_EFFR_IORB_bp": s_effr_iorb * 100,
        "A_d1_SOFR_EFFR": d1_a1,
        "A_d2_SOFR_EFFR": d2_a1,
        "A_d1_SOFR_IORB": d1_a2,
        "A_d2_SOFR_IORB": d2_a2,
    }

    return pos, neg, concl, snap


# -------------------------
# B) RRP / Reserves / TGA 줄다리기 (다음 단계)
# -------------------------
def trio_signals():
    return "B: None", "B: None", "B: (not implemented yet)", {}


# -------------------------
# C) Repo spread / Turn-end spike (다음 단계)
# -------------------------
def repo_signals():
    return "C: None", "C: None", "C: (not implemented yet)", {}


def liquidity_canary():
    """
    posL/negL/conclusion/liq_snapshot 을 리턴.
    지금은 A만 진짜 신호, B/C는 자리만.
    """
    posA, negA, conclA, snapA = corridor_signals()
    posB, negB, conclB, snapB = trio_signals()
    posC, negC, conclC, snapC = repo_signals()

    # Trigger는 “부정 신호 우선”으로 잡는 게 빠르고 날카로움
    pos = " | ".join([posA, posB, posC])
    neg = " | ".join([negA, negB, negC])

    # 결론도 A가 우선 (B/C 아직 미구현)
    conclusion = conclA

    snap = {}
    snap.update(snapA or {})
    snap.update(snapB or {})
    snap.update(snapC or {})

    return pos, neg, conclusion, snap
