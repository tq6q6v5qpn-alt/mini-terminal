# fred.py
import os
import requests

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

def liquidity_snapshot():
    ids = {
        "SOFR": "SOFR",
        "EFFR": "EFFR",
        "IORB": "IORB",
        "RRP":  "RRPONTSYD",
        "TGA":  "WTREGEN",
        "RESERVES": "WRESBAL",
    }
    out = {}
    for k, sid in ids.items():
        out[k] = latest(sid)
    return out
# fred.py (맨 아래에 추가)

def liquidity_snapshot():
    """
    FRED에서 핵심 유동성 스냅샷을 dict로 반환
    """
    series = {
        "SOFR": "SOFR",
        "EFFR": "EFFR",
        "IORB": "IORB",
        "RRP": "RRPONTSYD",
        "TGA": "WTREGEN",
        "RES": "WRESBAL",
        "TGCR": "TGCR",   # 가능하면 BGCR도 추가 가능
    }

    out = {}
    for k, sid in series.items():
        out[k] = latest(sid)
    return out


def liquidity_canary():
    """
    (+카나리아, -카나리아, 결론, raw스냅샷) 반환
    규칙: 양/기울기/가속(Δ/ΔΔ) 우선. (초기 보수 임계값)
    """
    s = liquidity_snapshot() or {}

    sofr = s.get("SOFR")
    iorb = s.get("IORB")
    tgcr = s.get("TGCR")
    rrp  = s.get("RRP")
    tga  = s.get("TGA")
    res  = s.get("RES")

    # 스프레드(단위: %)
    spr_sofr_iorb = (sofr - iorb) if (sofr is not None and iorb is not None) else None
    spr_tgcr_sofr = (tgcr - sofr) if (tgcr is not None and sofr is not None) else None

    pos = []
    neg = []

    # --- Negative (긴축/스트레스) ---
    # 1) 코리더 스트레스: SOFR이 IORB 위로 밀림(>=5bp)
    if spr_sofr_iorb is not None and spr_sofr_iorb >= 0.05:
        neg.append(f"SOFR-IORB↑ {spr_sofr_iorb:.2f}%")

    # 2) 레포 스파이크: TGCR-SOFR 스프레드(>=3bp)
    if spr_tgcr_sofr is not None and spr_tgcr_sofr >= 0.03:
        neg.append(f"TGCR-SOFR spike {spr_tgcr_sofr:.2f}%")

    # 3) RRP↑ & Res↓ (시장→흡수통)
    # (Δ는 main/state에 저장하는 게 더 정확하지만, 여기선 “레벨” 기반 힌트만)
    # → Δ/ΔΔ는 다음 단계에서 slope_acc를 fred에도 연결 가능
    # 지금은 빠르게 "레벨 신호"만 넣고 시작
    if rrp is not None and res is not None:
        # 레벨 자체로는 판단 약하니 결론엔 "변화 확인" 문구를 넣자
        pass

    # --- Positive (완화/리스크온) ---
    if spr_sofr_iorb is not None and spr_sofr_iorb <= 0.01:
        pos.append(f"SOFR-IORB tight {spr_sofr_iorb:.2f}%")

    # 결론(한 줄)
    if neg and not pos:
        conclusion = "Liquidity: 스트레스 쪽(코리더/레포 압력) — 방어적으로 확인."
    elif pos and not neg:
        conclusion = "Liquidity: 완화 쪽(코리더 안정) — 리스크온 여지."
    elif pos and neg:
        conclusion = "Liquidity: 혼재 — 스프레드/잔액 ‘변화(Δ/ΔΔ)’로 재판정 필요."
    else:
        conclusion = "Liquidity: 뚜렷한 이상 없음 — 다음 업데이트에서 Δ/ΔΔ 확인."

    pos_line = " + Canary: " + (" | ".join(pos) if pos else "None")
    neg_line = " - Canary: " + (" | ".join(neg) if neg else "None")

    return pos_line, neg_line, conclusion, s
