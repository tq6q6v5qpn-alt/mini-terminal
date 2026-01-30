# main.py
from datetime import datetime, timezone, timedelta
from state import get_num, set_num
from sources import price, btc_features
from analyzer import regime
from telegram import send

from fred import liquidity_canary  # ✅ A/B/C 포함된 canary

KST = timezone(timedelta(hours=9))


def slope_acc(key, v):
    """
    key의 현재 값 v를 state에 저장하면서
    d1 = 1차 변화(기울기, Δ)
    d2 = 2차 변화(가속, ΔΔ)
    """
    prev = get_num(key)
    prev_d = get_num(key + "_d")

    d1 = (v - prev) if (prev is not None) else 0.0
    d2 = (d1 - prev_d) if (prev_d is not None) else 0.0

    now = datetime.now(KST).isoformat()
    set_num(key, v, now)
    set_num(key + "_d", d1, now)
    return d1, d2


def run():
    # ===== Crypto Momentum =====
    btc = price("BTCUSDT") or 0.0
    eth = price("ETHUSDT") or 0.0

    f = btc_features()
    r5 = float(f.get("r5", 0.0))
    vol = float(f.get("vol_z", 0.0))
    acc = float(f.get("acc", 0.0))

    # ETH는 analyzer가 ETH_R5를 기대하는 케이스가 있어서 "KeyError 방지"용으로 키를 유지
    eth_ret_d1, eth_ret_d2 = slope_acc("ETH_PX", eth)  # 가격 변화(절대)
    # “리턴”처럼 쓰려면 퍼센트로:
    prev_eth = get_num("ETH_PX")
    eth_r5 = 0.0
    if prev_eth not in (None, 0):
        eth_r5 = (eth / prev_eth - 1.0) * 100.0

    # ===== Liquidity Canary (A/B/C) =====
    trigger_line, conclusion, liq = liquidity_canary()

    # ===== Build regime input dict =====
    # analyzer.regime()이 내부에서 특정 키를 요구할 수 있어 “기존 키 유지”가 안전
    m = {
        "BTC_R5": r5,
        "ETH_R5": eth_r5,   # ✅ KeyError 방지
        "VOL": vol,
        "ACC": acc,
    }

    # liq 값들을 “레벨”로도 넣고,
    # (너가 원하는 ‘기울기/가속’은 다음 단계에서 각 지표별 slope_acc로 확장하면 됨)
    if isinstance(liq, dict):
        for k, v in liq.items():
            if v is not None:
                m[k] = float(v)

    # ===== Message format (빠르고 정확하게) =====
    msg = (
        f"[Liquidity Canary]\n"
        f"Regime: {regime(m)}\n\n"
        f"[Trigger]\n"
        f"{trigger_line}\n\n"
        f"[Momentum]\n"
        f"BTC_R5={r5:.2f}% | VOL={vol:.2f}σ | ACC={acc:.2f}\n\n"
        f"[Conclusion]\n"
        f"{conclusion}"
    )

    send(msg)


if __name__ == "__main__":
    run()
