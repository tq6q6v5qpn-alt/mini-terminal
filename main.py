# main.py
import os, json, time
from typing import Any, Dict, Optional, Tuple

from fred import liquidity_canary

# =======================
# State (for slope/acc + streaks)
# =======================
STATE_PATH = "state.json"

def _load_state() -> Dict[str, Any]:
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_state(s: Dict[str, Any]) -> None:
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False)
    except Exception:
        pass

def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def slope_acc(key: str, value: float) -> Tuple[float, float]:
    """
    d1 = 이번 값 - 직전 값 (기울기)
    d2 = d1 - 직전 d1 (가속도)
    """
    s = _load_state()
    prev = s.get(key)
    prev_d1 = s.get(key + "_d1")

    d1 = 0.0 if prev is None else (value - float(prev))
    d2 = 0.0 if prev_d1 is None else (d1 - float(prev_d1))

    s[key] = value
    s[key + "_d1"] = d1
    _save_state(s)
    return d1, d2


# =======================
# Telegram sender (optional)
# =======================
def send(text: str) -> None:
    """
    네 환경에 이미 send()가 있으면 이 함수를 삭제하고 기존 send를 쓰면 됨.
    여기서는 안전하게 "없어도 죽지 않게" 콘솔 출력만.
    """
    print(text)


# =======================
# Regime: 아주 단순 버전 (너 코드에 이미 regime 있으면 교체 가능)
# =======================
def regime(m: Dict[str, Any]) -> str:
    # 기본은 Neutral. (나중에 네가 더 정교화 가능)
    return "Neutral"


# =======================
# Axis ON 감지(유의미 변화/차이)
# =======================
def detect_changes(m: Dict[str, Any]) -> Dict[str, str]:
    """
    반환: {"A":"...", "C":"...", "D":"..."} 처럼 켜진 축만.
    - "켜짐" = '차이(스프레드)' 혹은 '변화(Δ)' 혹은 '가속(ΔΔ)'이 임계치 이상
    """
    fired: Dict[str, str] = {}

    # ---- A: 정책 코리더 차이 (이미 fred에서 레벨로 판단하지만, 여기선 "차이" 자체로 ON)
    sofr = _safe_float(m.get("SOFR"))
    effr = _safe_float(m.get("EFFR"))
    iorb = _safe_float(m.get("IORB"))
    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr
        if spread_iorb_effr < 0.02:
            fired["A"] = "A ON: EFFR가 IORB 상단에 밀착(상단 압박)"
        elif abs(spread_sofr_effr) >= 0.10:
            fired["A"] = "A ON: SOFR-EFFR 이탈(코리더 균열)"

    # ---- B: 탱크 변화(큰 변화만)
    TH_TANK = 50_000.0  # 단위(백만$)가 아닐 수 있어. 데이터 스케일 보고 필요시 조정
    # 실제로는 ONRRP/TGA/RESERVES 레벨이 매우 큼. (FRED 레벨 단위가 보통 'Millions of Dollars')
    # 그래서 변화량 임계치는 보수적으로 크게 둠:
    TH_TANK = 20_000.0

    for key, label in [("ONRRP", "ONRRP"), ("TGA", "TGA"), ("RESERVES", "RES")]:
        v = _safe_float(m.get(key))
        if v is None:
            continue
        d1, d2 = slope_acc(key, float(v))
        m[key + "_d1"] = d1
        m[key + "_d2"] = d2
        if abs(d1) >= TH_TANK:
            fired["B"] = f"B ON: {label} 큰 이동(Δ={d1:+.0f})"
            break

    # ---- C: 레포 스프레드 차이
    bgcr = _safe_float(m.get("BGCR"))
    if (bgcr is not None) and (sofr is not None):
        repo_spread = bgcr - sofr
        if abs(repo_spread) >= 0.10:
            fired["C"] = "C ON: 레포 스프레드 확대(담보/현금 불균형)"

    # ---- D: 금리(2Y/10Y) 변화 + 커브(10-2) 변화
    for key in ("DGS2", "DGS10", "DTWEX"):
        v = _safe_float(m.get(key))
        if v is None:
            continue
        d1, d2 = slope_acc(key, float(v))
        m[key + "_d1"] = d1
        m[key + "_d2"] = d2

    dgs2 = _safe_float(m.get("DGS2"))
    dgs10 = _safe_float(m.get("DGS10"))
    if (dgs2 is not None) and (dgs10 is not None):
        curve = float(dgs10) - float(dgs2)
        cd1, cd2 = slope_acc("UST_CURVE_10_2", curve)
        m["UST_CURVE_10_2"] = curve
        m["UST_CURVE_10_2_d1"] = cd1
        m["UST_CURVE_10_2_d2"] = cd2

        # 임계치(직관): 금리는 0.05~0.15 움직임이 의미. 여기선 보수적으로 0.10
        if abs(m.get("DGS2_d1", 0.0)) >= 0.10 or abs(m.get("DGS10_d1", 0.0)) >= 0.10:
            fired["D"] = "D ON: 금리 레벨이 빠르게 이동(리스크 프라이싱 변곡)"
        elif abs(cd1) >= 0.10:
            fired["D"] = "D ON: 커브(10-2) 변형(침체/성장 기대 변화)"

    # ---- E: 달러(변화)
    dtwex = _safe_float(m.get("DTWEX"))
    if dtwex is not None:
        if abs(m.get("DTWEX_d1", 0.0)) >= 0.30:
            fired["E"] = "E ON: 달러 강도 급변(글로벌 유동성/리스크오프 톤)"

    return fired


# =======================
# Axis4: 의도/방치(연속 유지 + 미개입)
# =======================
def axis4_eval(fired: Dict[str, str], m: Dict[str, Any], streak_n: int = 3) -> Tuple[str, str]:
    """
    D(의도/방치):
    - A/B/C의 왜곡 신호가 N회 연속 유지되면 '방치 신호 ON' 가능성
    - 자동 문장: '지금은 기다릴 시간이다'
    """
    s = _load_state()
    # 무엇이 "왜곡"인가? A 또는 C 또는 B 큰 이동이 계속 뜨는지
    distort = 1 if (("A" in fired) or ("C" in fired) or ("B" in fired)) else 0
    prev_streak = int(s.get("DISTORT_STREAK", 0))
    streak = prev_streak + 1 if distort == 1 else 0
    s["DISTORT_STREAK"] = streak
    _save_state(s)

    axis4_line = ""
    wait_line = ""

    if streak >= streak_n:
        axis4_line = (
            f"D(의도/방치): A/B/C 왜곡이 {streak}회 연속 유지 → "
            "‘고칠 수 있는데’ 미개입이면 비대칭(누군가 이득) 가능성 ↑"
        )
        wait_line = (
            "지금은 ‘파도’가 아니라 ‘수문’ 구간(방치 신호 ON)이라, "
            "무리한 진입보다 관찰·대기(확인 후 행동)가 유리합니다."
        )
    else:
        axis4_line = f"D(의도/방치): 왜곡 연속성 낮음({streak}/{streak_n})"
        wait_line = "지금은 신호 확정 전(관찰 우선) 구간입니다."

    return axis4_line, wait_line


# =======================
# 역사적 직관 힌트(아키타입)
# =======================
def history_hint(fired: Dict[str, str], m: Dict[str, Any]) -> str:
    """
    엄밀한 예측이 아니라, 과거에 자주 같이 나타났던 '방향감'을 한 줄로.
    """
    # 우선순위: 스트레스/달러/단기금리
    if "C" in fired and "A" in fired:
        return "힌트: 단기자금/담보가 같이 조이기 시작하면(레포+코리더), 과거엔 ‘현금 선호↑·리스크 자산 변동성↑’ 쪽이 잦았습니다."
    if "E" in fired and (m.get("DTWEX_d1", 0.0) > 0):
        return "힌트: 달러 급강세는 과거에 ‘글로벌 유동성 수축·신흥/레버리지 압박’과 함께 오는 경우가 많았습니다."
    if "D" in fired and (m.get("DGS2_d1", 0.0) > 0):
        return "힌트: 2년물이 빨리 오르면(정책 재가격), 과거엔 ‘위험자산 숨고르기/밸류에이션 압박’ 쪽이 잦았습니다."
    if "B" in fired:
        return "힌트: 탱크(ONRRP/TGA/RES) 큰 이동은 ‘유동성 배관 재배치’ 신호일 수 있어, 다음 며칠의 방향이 중요합니다."
    return "힌트: 강한 패턴 결합은 아직 약합니다. (지금은 ‘확인’이 수익/리스크를 가릅니다.)"


# =======================
# Run
# =======================
def run() -> None:
    trigger_line, conclusion, liq = liquidity_canary()

    # 기본 m
    m: Dict[str, Any] = {}

    # liq 값을 m에 반영
    if isinstance(liq, dict):
        for k, v in liq.items():
            fv = _safe_float(v)
            if fv is not None:
                m[k] = fv

    # 유의미 변화 감지
    fired = detect_changes(m)

    # 4번 축(의도/방치)
    axis4_line, wait_line = axis4_eval(fired, m, streak_n=3)

    # 역사적 직관 힌트
    hint = history_hint(fired, m)

    # 메시지 구성(줄 안맞음 방지: msg+= 방식)
    msg = ""
    msg += "[Liquidity Canary]\n"
    msg += f"Regime: {regime(m)}\n\n"

    msg += "[Trigger]\n"
    msg += f"{trigger_line}\n\n"

    msg += "[Fired]\n"
    if fired:
        for ax, text in fired.items():
            msg += f"- {text}\n"
    else:
        msg += "- None (유의미한 변화 감지 없음)\n"
    msg += "\n"

    msg += "[Axis4]\n"
    msg += f"{axis4_line}\n"
    msg += f"{wait_line}\n\n"

    msg += "[History Hint]\n"
    msg += f"{hint}\n\n"

    # D/E 숫자 요약
    msg += "[Axis Values]\n"
    if m.get("DGS2") is not None:
        msg += f"DGS2={m.get('DGS2'):.2f}%  Δ={m.get('DGS2_d1',0.0):+.3f}  ΔΔ={m.get('DGS2_d2',0.0):+.3f}\n"
    if m.get("DGS10") is not None:
        msg += f"DGS10={m.get('DGS10'):.2f}%  Δ={m.get('DGS10_d1',0.0):+.3f}  ΔΔ={m.get('DGS10_d2',0.0):+.3f}\n"
    if m.get("UST_CURVE_10_2") is not None:
        msg += f"Curve(10-2)={m.get('UST_CURVE_10_2'):+.2f}%p  Δ={m.get('UST_CURVE_10_2_d1',0.0):+.3f}  ΔΔ={m.get('UST_CURVE_10_2_d2',0.0):+.3f}\n"
    if m.get("DTWEX") is not None:
        msg += f"USD(DTWEX)={m.get('DTWEX'):.2f}  Δ={m.get('DTWEX_d1',0.0):+.3f}  ΔΔ={m.get('DTWEX_d2',0.0):+.3f}\n"
    msg += "\n"

    msg += "[Conclusion]\n"
    msg += f"{conclusion}"

    send(msg)


if __name__ == "__main__":
    run()
