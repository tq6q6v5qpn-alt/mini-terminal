from datetime import datetime, timezone, timedelta
from state import get_num, set_num
from sources import price, funding, oi, klines, btc_features
from features import candle_features
from analyzer import regime
from telegram import send
from fred import liquidity_snapshot
KST = timezone(timedelta(hours=9))

def d(k, v):
    p = get_num(k)
    set_num(k, v, datetime.now(KST).isoformat())
    return v - p if p is not None else 0

def run():
    btc = price('BTCUSDT')
    eth = price('ETHUSDT')

    f = btc_features()
    r5  = f["r5"]
    vol = f["vol_z"]
    acc = f["acc"]
liq = liquidity_snapshot()
    m = {
    'BTC_R5': r5,
    'ETH_R5': d('ETH', eth),
    'VOL': vol,
    'ACC': acc,
    **liq
}

    msg = (
        f"Regime: {regime(m)}\n"
        f"BTC_R5:{r5:.2f}% VOL:{vol:.2f} ACC:{acc:.2f}"
    )

    send(msg)

if __name__ == "__main__":
    run()
