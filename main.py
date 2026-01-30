from datetime import datetime, timezone, timedelta
from state import get_num, set_num
from sources import price, funding, oi, klines, btc_features
from analyzer import regime
from telegram import send
from fred import liquidity_snapshot

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

    liq = liquidity_snapshot()  # dict 형태(예: {"SOFR":..., "RRP":..., ...})

    # === 여기서부터: 상태 변화(Δ)만 저장/계산 ===
    eth_d1, eth_d2 = slope_acc("ETH", eth if eth is not None else 0.0)

    # BTC_R5 / VOL / ACC도 “양/기울기/가속” 프레임으로 가려면
    # 다음 단계에서 slope_acc로 바꿀 거고, 지금은 일단 기존 값 유지

    m = {
        "BTC_R5": r5,
        "ETH_R5": eth_d1,   # (이름은 임시) 지금은 ETH 가격 변화량을 넣은 상태
        "VOL": vol,
        "ACC": acc,
        **(liq or {}),
    }

    msg = (
        f"Regime: {regime(m)}\n"
        f"BTC_R5:{r5:.2f}% VOL:{vol:.2f} ACC:{acc:.2f}"
    )
    send(msg)


if __name__ == "__main__":
    run()
