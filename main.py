# main.py
import os
import math
import requests
from typing import Dict, Any, Optional, List

from fred import liquidity_canary
from sources import get_crypto_prices_usd
from features import slope_acc
from state import load_state, save_state
from analyzer import regime


def send_telegram(text: str) -> bool:
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return True
    except Exception:
        return False


def _roll_push(arr: List[float], x: float, maxlen: int) -> List[float]:
    arr = list(arr or [])
    arr.append(float(x))
    if len(arr) > maxlen:
        arr = arr[-maxlen:]
    return arr


def _std(xs: List[float]) -> float:
    if not xs or len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    return math.sqrt(v)


def run() -> None:
    # 1) Liquidity (A/B/C/D/E)
    trigger_line, conclusion, liq = liquidity_canary()

    # 2) Crypto prices
    px = get_crypto_prices_usd()
    btc = px.get("BTC")
    eth = px.get("ETH")

    # 3) Load state (for momentum)
    state = load_state()
    mom = state.get("momentum", {})
    if not isinstance(mom, dict):
        mom = {}

    btc_hist = mom.get("btc_hist", [])
    eth_hist = mom.get("eth_hist", [])
    ret_hist = mom.get("btc_ret_hist", [])

    # update histories
    if btc is not None:
        btc_hist = _roll_push(btc_hist, btc, 30)
    if eth is not None:
        eth_hist = _roll_push(eth_hist, eth, 30)

    # compute BTC_R5 using 5-step ago
    r5 = 0.0
    if btc is not None and len(btc_hist) >= 6:
        p_now = btc_hist[-1]
        p_5 = btc_hist[-6]
        if p_5 != 0:
            r5 = (p_now / p_5 - 1.0) * 100.0

    # compute 1-step return for vol/acc
    r1 = 0.0
    if btc is not None and len(btc_hist) >= 2:
        p0 = btc_hist[-2]
        p1 = btc_hist[-1]
        if p0 != 0:
            r1 = (p1 / p0 - 1.0) * 100.0

    ret_hist = _roll_push(ret_hist, r1, 25)
    vol = _std(ret_hist)  # σ of 1-step returns (simple)
    # acceleration: change in r1 (slope of return)
    acc = 0.0
    if len(ret_hist) >= 2:
        acc = ret_hist[-1] - ret_hist[-2]

    # save momentum state
    mom["btc_hist"] = btc_hist
    mom["eth_hist"] = eth_hist
    mom["btc_ret_hist"] = ret_hist
    state["momentum"] = mom
    save_state(state)

    # 4) Build regime input dict
    m: Dict[str, Any] = {
        "BTC_R5": float(r5),
        "VOL": float(vol),
        "ACC": float(acc),
    }

    # 5) Add liq levels into m (only non-None)
    if isinstance(liq, dict):
        for k, v in liq.items():
            if v is not None:
                try:
                    m[k] = float(v)
                except Exception:
                    pass

    # 6) slope/acc for DGS2, DGS10, DTWEX + curve(10-2)
    # (값이 있을 때만)
    if m.get("DGS2") is not None:
        d1, d2 = slope_acc("DGS2", float(m["DGS2"]))
        m["DGS2_d1"], m["DGS2_d2"] = d1, d2

    if m.get("DGS10") is not None:
        d1, d2 = slope_acc("DGS10", float(m["DGS10"]))
        m["DGS10_d1"], m["DGS10_d2"] = d1, d2

    if m.get("DTWEX") is not None:
        d1, d2 = slope_acc("DTWEX", float(m["DTWEX"]))
        m["DTWEX_d1"], m["DTWEX_d2"] = d1, d2

    if (m.get("DGS10") is not None) and (m.get("DGS2") is not None):
        curve = float(m["DGS10"]) - float(m["DGS2"])
        cd1, cd2 = slope_acc("UST_CURVE_10_2", curve)
        m["UST_CURVE_10_2"] = curve
        m["UST_CURVE_10_2_d1"] = cd1
        m["UST_CURVE_10_2_d2"] = cd2

    # 7) Format message (한 번에)
    reg = regime(m)

    axis_lines = []
    axis_lines.append(f"DGS2  Δ={m.get('DGS2_d1', 0.0):+.3f}  ΔΔ={m.get('DGS2_d2', 0.0):+.3f}")
    axis_lines.append(f"DGS10 Δ={m.get('DGS10_d1', 0.0):+.3f}  ΔΔ={m.get('DGS10_d2', 0.0):+.3f}")
    axis_lines.append(f"USD   Δ={m.get('DTWEX_d1', 0.0):+.3f}  ΔΔ={m.get('DTWEX_d2', 0.0):+.3f}")
    axis_lines.append(f"10-2  Δ={m.get('UST_CURVE_10_2_d1', 0.0):+.3f}  ΔΔ={m.get('UST_CURVE_10_2_d2', 0.0):+.3f}")

    msg = (
        "[Liquidity Canary]\n"
        f"Regime: {reg}\n\n"
        "[Trigger]\n"
        f"{trigger_line}\n\n"
        "[Momentum]\n"
        f"BTC_R5={r5:+.2f}% | VOL={vol:.2f}σ | ACC={acc:+.2f}\n\n"
        "[Axis]\n"
        + "\n".join(axis_lines)
        + "\n\n"
        "[Conclusion]\n"
        f"{conclusion}"
    )

    send_telegram(msg)


if __name__ == "__main__":
    run()
