import os
import requests
from datetime import datetime, timezone, timedelta

from state import get_num, set_num

KST = timezone(timedelta(hours=9))
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# =========================
# 튜닝 포인트 (처음은 보수적으로)
# =========================
# A/C: bp 단위 변화 임계치
TH_A_D1 = 2.0     # Δ 2bp
TH_A_D2 = 1.5     # ΔΔ 1.5bp

TH_C_D1 = 3.0     # 레포스프레드 Δ 3bp
TH_C_D2 = 2.0     # 레포스프레드 ΔΔ 2bp

# B: 잔액 변화(절대값) 임계치
# (FRED 단위가 시리즈마다 다를 수 있어 처음엔 크게 잡음. 필요시 낮춰서 민감도↑)
TH_B_RRP = 50.0       # RRP 변화 임계치(대략 "billion" 단위일 가능성)
TH_B_TGA = 20.0       # TGA 변화 임계치
TH_B_RES = 50.0       # Reserves 변화 임계치

# =========================
# FRED series IDs
# =========================
# A: 금리 코리더
SER_SOFR = "SOFR"
SER_EFFR = "EFFR"
SER_IORB = "IORB"

# B: 유동성 통로(잔액)
SER_RRP = "RRPONTSYD"   # ON RRP (Total)
SER_TGA = "WTREGEN"     # Treasury General Account
SER_RES = "WRESBAL"     # Reserve Balances with Federal Reserve Banks

# C: 레포/담보 프린트
SER_TGCR = "TGCR"       # Tri-Party General Collateral Rate
SER_BGCR = "BGCR"       # Broad General Collateral Rate
# SOFR는 A에서 이미


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
    state에 (레벨, Δ, ΔΔ)를 저장/계산
    d1 = v - prev
    d2 = d1 - prev_d1
    """
    prev = get_num(key)
    prev_d = get_num(key + "_d")

    d1 = (v - prev) if (prev is not None) else 0.0
    d2 = (d1 - prev_d) if (prev_d is not None) else 0.0

    now = datetime.now(KST).isoformat()
    set_num(key, v, now)
    set_num(key + "_d", d1, now)
    return d1, d2


def _pick_max_abs(items, idx=2):
    # items: list of tuples, choose max abs(items[i][idx])
    return max(items, key=lambda x: abs(x[idx])) if items else None


def _fmt_bp(x):
    return "NA" if x is None else f"{x:+.1f}bp"


def _fmt_d(x):
    return f"{x:+.1f}"


def liquidity_snapshot():
    """
    레벨(원시값)만 수집 (A/B/C 모두에 필요한 최소치)
    """
    return {
        # A
        "SOFR": latest(SER_SOFR),
        "EFFR": latest(SER_EFFR),
        "IORB": latest(SER_IORB),

        # B
        "RRP": latest(SER_RRP),
        "TGA": latest(SER_TGA),
        "RES": latest(SER_RES),

        # C
        "TGCR": latest(SER_TGCR),
        "BGCR": latest(SER_BGCR),
    }


def liquidity_canary():
    """
    출력 포맷:
      posL: "A: ... | B: ... | C: ..."
      negL: "A: ... | B: ... | C: ..."
      conclL: 1문장 결론
      liq: 레벨 + 파생(스프레드/Δ/ΔΔ) 딕트
    """
    liq = liquidity_snapshot()

    # =========================
    # A) Policy Corridor (SOFR/EFFR vs IORB)
    # =========================
    sofr = liq.get("SOFR")
    effr = liq.get("EFFR")
    iorb = liq.get("IORB")

    a_pos = "A: None"
    a_neg = "A: None"
    a_concl = "A: 데이터 부족"

    a_candidates = []

    if sofr is not None and iorb is not None:
        sp = (sofr - iorb) * 100.0  # bp
        d1, d2 = slope_acc("A_SP_SOFR_IORB_BP", sp)
        liq["A_SP_SOFR_IORB_BP"] = sp
        liq["A_SP_SOFR_IORB_BP_D1"] = d1
        liq["A_SP_SOFR_IORB_BP_D2"] = d2
        a_candidates.append(("SOFR-IORB", sp, d1, d2))

    if effr is not None and iorb is not None:
        sp = (effr - iorb) * 100.0  # bp
        d1, d2 = slope_acc("A_SP_EFFR_IORB_BP", sp)
        liq["A_SP_EFFR_IORB_BP"] = sp
        liq["A_SP_EFFR_IORB_BP_D1"] = d1
        liq["A_SP_EFFR_IORB_BP_D2"] = d2
        a_candidates.append(("EFFR-IORB", sp, d1, d2))

    rep = _pick_max_abs(a_candidates, idx=2)  # |Δ| 최대를 대표로
    if rep:
        name, lvl, d1, d2 = rep
        # 압력↑: 스프레드가 벌어지는 방향(+Δ/+ΔΔ)
        if (d1 >= TH_A_D1) or (d2 >= TH_A_D2):
            a_neg = f"A-: corridor 압력↑ ({name}={_fmt_bp(lvl)}, Δ={_fmt_d(d1)}bp, ΔΔ={_fmt_d(d2)}bp)"
            a_concl = "A: 코리더 압력 신호(현장 조달/담보 타이트 가능)"
        # 완화↑: 스프레드가 줄어드는 방향(-Δ/-ΔΔ)
        elif (d1 <= -TH_A_D1) or (d2 <= -TH_A_D2):
            a_pos = f"A+: corridor 완화↑ ({name}={_fmt_bp(lvl)}, Δ={_fmt_d(d1)}bp, ΔΔ={_fmt_d(d2)}bp)"
            a_concl = "A: 코리더 완화 신호(현장 압력 완화 가능)"
        else:
            a_concl = "A: 정책 코리더 정상 범위(Δ/ΔΔ 급변 없음)"
    else:
        a_concl = "A: SOFR/EFFR/IORB 수집 불가"

    # =========================
    # B) RRP ↔ Reserves ↔ TGA (잔액의 줄다리기)
    # =========================
    rrp = liq.get("RRP")
    tga = liq.get("TGA")
    res = liq.get("RES")

    b_pos = "B: None"
    b_neg = "B: None"
    b_concl = "B: 데이터 부족"

    # 레벨 자체도 저장해두면(나중에) 유용하지만, 지금은 변화(Δ/ΔΔ) 중심
    b_moves = {}

    def _track_bal(tag, key, val):
        if val is None:
            return None
        d1, d2 = slope_acc(key, val)
        liq[f"{tag}"] = val
        liq[f"{tag}_D1"] = d1
        liq[f"{tag}_D2"] = d2
        b_moves[tag] = (val, d1, d2)
        return (val, d1, d2)

    _track_bal("B_RRP", "B_RRP", rrp)
    _track_bal("B_TGA", "B_TGA", tga)
    _track_bal("B_RES", "B_RES", res)

    if b_moves:
        # "양" 우선: 세 개 중 |Δ|가 제일 큰 항목을 대표 프린트로
        repB = max(b_moves.items(), key=lambda kv: abs(kv[1][1]))
        tag, (lvl, d1, d2) = repB

        # 휴리스틱(발표 전 선행 흔적):
        # - NEG(드레인): TGA↑(재무부로 자금 흡수) 또는 RES↓(준비금 감소)가 큰 폭 + 가속
        # - POS(릴리즈): RRP↓(흡수통 풀림) 또는 RES↑(준비금 회복)가 큰 폭 + 가속
        drain = False
        release = False

        # 각 항목별 임계치 적용
        if "B_TGA" in b_moves:
            _, td1, td2 = b_moves["B_TGA"]
            if (td1 >= TH_B_TGA) or (td2 >= TH_B_TGA * 0.6):
                drain = True
        if "B_RES" in b_moves:
            _, rd1, rd2 = b_moves["B_RES"]
            if (rd1 <= -TH_B_RES) or (rd2 <= -TH_B_RES * 0.6):
                drain = True
            if (rd1 >= TH_B_RES) or (rd2 >= TH_B_RES * 0.6):
                release = True
        if "B_RRP" in b_moves:
            _, xd1, xd2 = b_moves["B_RRP"]
            if (xd1 <= -TH_B_RRP) or (xd2 <= -TH_B_RRP * 0.6):
                release = True
            if (xd1 >= TH_B_RRP) or (xd2 >= TH_B_RRP * 0.6):
                drain = True  # 흡수통이 커지는 방향

        # 대표 문구
        if drain and not release:
            b_neg = f"B-: 잔액 드레인 징후 ({tag} Δ={_fmt_d(d1)} / ΔΔ={_fmt_d(d2)})"
            b_concl = "B: RRP/준비금/TGA 줄다리기에서 '흡수/드레인' 신호"
        elif release and not drain:
            b_pos = f"B+: 잔액 릴리즈 징후 ({tag} Δ={_fmt_d(d1)} / ΔΔ={_fmt_d(d2)})"
            b_concl = "B: RRP/준비금/TGA 줄다리기에서 '완화/릴리즈' 신호"
        elif drain and release:
            b_neg = f"B±: 혼재(드레인·릴리즈 동시) ({tag} Δ={_fmt_d(d1)} / ΔΔ={_fmt_d(d2)})"
            b_concl = "B: 잔액 흐름 혼재(해석 유보, 다음 업데이트 대기)"
        else:
            b_concl = "B: 잔액 급변 없음(Δ/ΔΔ 의미있는 변화 없음)"
    else:
        b_concl = "B: RRP/TGA/RES 수집 불가"

    # =========================
    # C) Repo Spreads / Turn-end spike (TGCR/BGCR vs SOFR)
    # =========================
    tgcr = liq.get("TGCR")
    bgcr = liq.get("BGCR")
    sofr2 = liq.get("SOFR")  # 이미 있음

    c_pos = "C: None"
    c_neg = "C: None"
    c_concl = "C: 데이터 부족"

    c_candidates = []

    def _repo_spread(name, key, a, b):
        if a is None or b is None:
            return None
        sp = (a - b) * 100.0  # bp
        d1, d2 = slope_acc(key, sp)
        liq[f"{key}"] = sp
        liq[f"{key}_D1"] = d1
        liq[f"{key}_D2"] = d2
        c_candidates.append((name, sp, d1, d2))
        return sp, d1, d2

    _repo_spread("TGCR-SOFR", "C_SP_TGCR_SOFR_BP", tgcr, sofr2)
    _repo_spread("BGCR-SOFR", "C_SP_BGCR_SOFR_BP", bgcr, sofr2)

    repC = _pick_max_abs(c_candidates, idx=2)
    if repC:
        name, lvl, d1, d2 = repC
        # 스프레드 급등(+) = 담보/현금 타이트(턴엔드 포함)로 해석되는 경우 많음
        if (d1 >= TH_C_D1) or (d2 >= TH_C_D2):
            c_neg = f"C-: repo 스파이크↑ ({name}={_fmt_bp(lvl)}, Δ={_fmt_d(d1)}bp, ΔΔ={_fmt_d(d2)}bp)"
            c_concl = "C: 레포 스프레드 스파이크(턴엔드/담보 타이트 선행 가능)"
        elif (d1 <= -TH_C_D1) or (d2 <= -TH_C_D2):
            c_pos = f"C+: repo 완화↑ ({name}={_fmt_bp(lvl)}, Δ={_fmt_d(d1)}bp, ΔΔ={_fmt_d(d2)}bp)"
            c_concl = "C: 레포 스프레드 완화(담보/현금 압력 완화 가능)"
        else:
            c_concl = "C: 레포 스프레드 급변 없음(Δ/ΔΔ 의미있는 변화 없음)"
    else:
        c_concl = "C: TGCR/BGCR/SOFR 수집 불가"

    # =========================
    # 최종 출력 (A|B|C 라인 + 결론 1문장)
    # =========================
    posL = f"{a_pos} | {b_pos} | {c_pos}"
    negL = f"{a_neg} | {b_neg} | {c_neg}"

    # 결론 우선순위: NEG가 있으면 NEG 중심, 아니면 POS, 아니면 A/B/C 정상 요약
    if ("A-" in a_neg) or ("B-" in b_neg) or ("C-" in c_neg):
        conclL = " / ".join([x for x in [a_concl, b_concl, c_concl] if "신호" in x or "스파이크" in x or "드레인" in x])
        conclL = conclL if conclL else "A/B/C 중 부정 조기신호 감지"
    elif ("A+" in a_pos) or ("B+" in b_pos) or ("C+" in c_pos):
        conclL = " / ".join([x for x in [a_concl, b_concl, c_concl] if "완화" in x or "릴리즈" in x])
        conclL = conclL if conclL else "A/B/C 중 완화 조기신호 감지"
    else:
        # 정상/유보 문구는 너무 길어지지 않게 A 중심 + B/C 상태
        conclL = f"{a_concl} / {b_concl} / {c_concl}"

    return posL, negL, conclL, liq
