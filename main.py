# main.py
import json
import os
from typing import Any, Dict, Optional, Tuple

from fred import liquidity_canary


STATE_PATH = os.getenv("STATE_PATH", "/tmp/canary_state.json")
AXIS4_N = int(os.getenv("AXIS4_N", "3"))  # 5분 크론이면 3회=15분 연속 유지


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
        pass  # 크론 죽이면 안 됨


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _delta(key: str, v: Optional[float]) -> float:
    """
    값 v의 전회 대비 변화(Δ)를 저장/반환. (가속은 지금 단계에선 불필요)
    """
    if v is None:
        return 0.0
    s = _load_state()
    prev = _safe_float(s.get(key))
    s[key] = float(v)
    _save_state(s)
    if prev is None:
        return 0.0
    return float(v) - prev


def axis4_eval(liq: Dict[str, Any]) -> Tuple[bool, str, str]:
    """
    4번 축(의도/방치) 평가:
    - A/B/C 왜곡(압박/완화) 방향이 연속 N회 유지
    - "고칠 수 있는데" 미개입은 직접 데이터로 못 보니, 여기서는 '지속성'으로 대체
    - 비대칭 수혜(달러 강세/커브 플랫 등) 동반 시 확신 ↑
    반환: (axis4_on, one_line_D, wait_sentence)
    """
    # --- 숫자 꺼내기 ---
    sofr = _safe_float(liq.get("SOFR"))
    effr = _safe_float(liq.get("EFFR"))
    iorb = _safe_float(liq.get("IORB"))

    onrrp = _safe_float(liq.get("ONRRP"))
    tga = _safe_float(liq.get("TGA"))
    reserves = _safe_float(liq.get("RESERVES"))

    bgcr = _safe_float(liq.get("BGCR"))

    dgs2 = _safe_float(liq.get("DGS2"))
    dgs10 = _safe_float(liq.get("DGS10"))
    dtwex = _safe_float(liq.get("DTWEX"))

    # --- A: 코리더 압박 방향(타이트 + / 완화 - / 중립 0) ---
    A_dir = 0
    A_distort = False
    if (sofr is not None) and (effr is not None) and (iorb is not None):
        spread_sofr_effr = sofr - effr
        spread_iorb_effr = iorb - effr

        # 타이트(+) 후보: EFFR가 IORB에 바짝(상단 압박) or SOFR-EFFR 크게 +
        if (spread_iorb_effr < 0.02) or (spread_sofr_effr >= 0.10):
            A_dir = +1
            A_distort = True
        # 완화(-) 후보: SOFR-EFFR 크게 -
        elif spread_sofr_effr <= -0.10:
            A_dir = -1
            A_distort = True

    # --- C: 레포 스프레드(타이트 + / 완화 -) ---
    C_dir = 0
    C_distort = False
    if (bgcr is not None) and (sofr is not None):
        repo_spread = bgcr - sofr
        if repo_spread >= 0.10:
            C_dir = +1
            C_distort = True
        elif repo_spread <= -0.10:
            C_dir = -1
            C_distort = True

    # --- B: 탱크 3종은 '변화(Δ)'로만 간단 판정(큰 움직임만) ---
    # 단위가 커서 임계값은 크게(초기값). 필요하면 나중에 조정.
    B_dir = 0
    B_distort = False
    if (onrrp is not None) and (tga is not None) and (reserves is not None):
        d_onrrp = _delta("B_ONRRP", onrrp)
        d_tga = _delta("B_TGA", tga)
        d_res = _delta("B_RES", reserves)

        TH = 50_000_000_000.0  # 500억 달러 수준 변화만 잡기(초기값)

        # 타이트(+) 후보: RRP 증가(현금 주차), TGA 증가(세금/발행으로 흡수), RES 감소(은행 현금 얇아짐)
        tight_score = 0
        if d_onrrp >= TH:
            tight_score += 1
        if d_tga >= TH:
            tight_score += 1
        if d_res <= -TH:
            tight_score += 1

        # 완화(-) 후보: RRP 감소(현금 풀림), TGA 감소(정부 지출), RES 증가(은행 현금 늘어남)
        ease_score = 0
        if d_onrrp <= -TH:
            ease_score += 1
        if d_tga <= -TH:
            ease_score += 1
        if d_res >= TH:
            ease_score += 1

        if tight_score >= 1 and tight_score > ease_score:
            B_dir = +1
            B_distort = True
        elif ease_score >= 1 and ease_score > tight_score:
            B_dir = -1
            B_distort = True

    # --- 방향 합치기: A/B/C 중 "왜곡"만 방향 투표 ---
    dirs = []
    if A_distort:
        dirs.append(A_dir)
    if B_distort:
        dirs.append(B_dir)
    if C_distort:
        dirs.append(C_dir)

    any_distort = len(dirs) > 0
    net_dir = _sign(sum(dirs))  # +1 타이트 쏠림, -1 완화 쏠림, 0 혼재/중립

    # --- 비대칭 수혜(프록시): USD 강세 or 커브 더 플랫/인버전(리스크에 보통 불리) ---
    asym = False
    if dtwex is not None:
        d_usd = _delta("E_DTWEX", dtwex)
        if d_usd > 0:
            asym = True

    if (dgs10 is not None) and (dgs2 is not None):
        curve = dgs10 - dgs2
        d_curve = _delta("D_CURVE_10_2", curve)
        # 커브가 더 플랫(↓)이면 긴장 프록시
        if d_curve < 0:
            asym = True

    # --- 지속성(방치) 추적 ---
    s = _load_state()
    prev_dir = int(s.get("axis4_prev_dir", 0) or 0)
    streak = int(s.get("axis4_streak", 0) or 0)

    if any_distort and net_dir != 0 and net_dir == prev_dir:
        streak += 1
    elif any_distort and net_dir != 0:
        streak = 1
    else:
        streak = 0
        net_dir = 0

    s["axis4_prev_dir"] = net_dir
    s["axis4_streak"] = streak
    _save_state(s)

    # --- 최종 판정 ---
    axis4_on = (streak >= AXIS4_N) and any_distort and (net_dir != 0) and asym

    D_line = (
        f"D(의도/방치): A/B/C 왜곡이 {streak}회 연속 유지 + ‘고칠 수 있는데’ 미개입(지속성) → "
        f"누군가 이득 보는 구조(비대칭) 가능성 ↑"
    )

    wait_sentence = (
        "지금은 ‘파도’가 아니라 ‘수문’ 구간(방치 신호 ON)이라, "
        "무리한 진입보다 관찰·대기(확인 후 행동)가 유리합니다."
    )

    return axis4_on, D_line, wait_sentence


def run():
    trigger_line, conclusion, liq = liquidity_canary()

    axis4_on, D_line, wait_sentence = axis4_eval(liq if isinstance(liq, dict) else {})

    msg = (
        "[Liquidity Canary]\n"
        "[Trigger]\n"
        f"{trigger_line}\n\n"
        "[Conclusion]\n"
        f"{conclusion}\n"
    )

    # ✅ 4번 축을 코드로 붙이기
    if axis4_on:
        msg += (
            "\n[Axis-4]\n"
            f"{D_line}\n\n"
            "[Action]\n"
            f"{wait_sentence}\n"
        )
    else:
        msg += "\n[Axis-4]\nD(의도/방치): OFF (지속/비대칭 조건 미충족)\n"

    print(msg)


if __name__ == "__main__":
    run()
