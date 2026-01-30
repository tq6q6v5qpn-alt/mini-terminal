from datetime import datetime, timezone, timedelta
from state import get_num, set_num
from sources import price, funding, oi, klines, btc_features
from analyzer import regime
from telegram import send
from fred import liquidity_canary

KST = timezone(timedelta(hours=9))


def slope_acc(key, v):
    """
    key의 현재 값 v를 state에 저장하면서
    d1 = 1차 변화(기울기, Δ)
    d2 = 2차 변화(가속, ΔΔ)
    를 계산해 반환
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
    btc = price("BTCUSDT")
    eth = price("ETHUSDT")

    f = btc_features()
    r5 = f["r5"]
    vol = f["vol_z"]
    acc = f["acc"]

    # 유동성 카나리아 (A,B,C의 출발점)
    posL, negL, conclL, liq = liquidity_canary()

    # === 상태 변화 (Δ, ΔΔ) ===
    eth_d1, eth_d2 = slope_acc("ETH", eth if eth is not None else 0.0)

    # Regime 입력용 맵
    m = {
        "BTC_R5": r5,
        "ETH_R5": eth_d1,
        "VOL": vol,
        "ACC": acc,
        **(liq or {}),
    }

    # === Trigger 선택 ===
    trigger = posL if (posL and "None" not in posL) else negL

    # === 메시지 ===
    msg = (
        f"[Liquidity Canary]\n"
        f"Regime: {regime(m)}\n\n"
        f"[Trigger]\n"
        f"{trigger}\n\n"
        f"[Momentum]\n"
        f"BTC_R5={r5:.2f}% | VOL={vol:.2f}σ | ACC={acc:.2f}\n\n"
        f"[Conclusion]\n"
        f"{conclL}"
    )

    send(msg)


if __name__ == "__main__":
    run()
