# main.py
import os
import json
import time
import requests
from math import log, sqrt

from fred import liquidity_canary

STATE_PATH = "/tmp/state.json"


# --------- (옵션) analyzer.regime 있으면 사용 ---------
def _regime_fallback(m: dict) -> str:
    # 아주 단순: VOL/ACC 기반
    vol = m.get("VOL")
    acc = m.get("ACC")
    if vol is None or acc is None:
        return "Neutral"
    if vol >= 2.0 and acc < 0:
        return "Risk-Off"
    if vol >= 2.0 and acc > 0:
        return "Risk-On"
    return "Neutral"


try:
    from analyzer import regime as analyzer_regime
except Exception:
    analyzer_regime = None


def regime(m: dict) -> str:
    if analyzer_regime:
        try:
            return analyzer_regime(m)
        except Exception:
            return _regime_fallback(m)
    return _regime_fallback(m)


# --------- Telegram sender ---------
def send(msg: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        # 텔레그램 미설정이면 로그로만
        print(msg)
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg}
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print("send() failed:", e)
        print(msg)


# --------- Price + simple momentum (BTC 5m return, VOL z, ACC) ---------
def _load_state():
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(s: dict):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f)
    except Exception:
        pass


def _coingecko_price(coin_id: str) -> float | None:
    # Render에서는 외부 요청 가능. (키 필요 없음)
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {"ids": coin_id, "vs_currencies": "usd"}
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return float(r.json()[coin_id]["usd"])
    except Exception:
        return None


def _zscore(xs):
    if len(xs) < 10:
        return None
    m = sum(xs) / len(xs)
    v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
    sd = sqrt(v) if v > 0 else 0.0
    if sd == 0:
        return 0.0
    return (xs[-1] - m) / sd


def run():
    # --------- crypto metrics ---------
    st = _load_state()
    now = int(time.time())

    btc = _coingecko_price("bitcoin")
    eth = _coingecko_price("ethereum")

    # price history (keep last ~200 points)
    hist = st.get("hist", [])
    if btc is not None:
        hist.append({"t": now, "btc": btc, "eth": eth})
        hist = hist[-200:]
        st["hist"] = hist
        _save_state(st)

    # BTC_R5: last-to-prev sample return (percent)
    r5 = 0.0
    eth_r5 = 0.0
    vol_z = 0.0
    acc = 0.0

    if len(hist) >= 2 and hist[-1].get("btc") and hist[-2].get("btc"):
        p0 = float(hist[-2]["btc"])
        p1 = float(hist[-1]["btc"])
        r5 = (p1 / p0 - 1.0) * 100.0

    if len(hist) >= 2 and hist[-1].get("eth") and hist[-2].get("eth"):
        e0 = hist[-2].get("eth")
        e1 = hist[-1].get("eth")
        if e0 and e1:
            eth_r5 = (float(e1) / float(e0) - 1.0) * 100.0

    # VOL: zscore of log returns of BTC
    rets = []
    for i in range(1, len(hist)):
        a = hist[i - 1].get("btc")
        b = hist[i].get("btc")
        if a and b and float(a) > 0 and float(b) > 0:
            rets.append(log(float(b) / float(a)))
    vz = _zscore(rets)
    vol_z = float(vz) if vz is not None else 0.0

    # ACC: second difference of log price (proxy acceleration)
    if len(hist) >= 3:
        pA = hist[-3].get("btc")
        pB = hist[-2].get("btc")
        pC = hist[-1].get("btc")
        if pA and pB and pC and float(pA) > 0 and float(pB) > 0 and float(pC) > 0:
            d1 = log(float(pB) / float(pA))
            d2 = log(float(pC) / float(pB))
            acc = (d2 - d1)

    # --------- Liquidity Canary (A/B/C) ---------
    # ✅ 여기서 “항상 3개”만 받는다 (에러 방지 핵심)
    trigger_line, conclusion, liq = liquidity_canary()

    # analyzer.regime()이 내부에서 특정 키를 요구할 수 있어 안전하게 넣어줌
    m = {
        "BTC_R5": r5,
        "ETH_R5": eth_r5,
        "VOL": vol_z,
        "ACC": acc,
    }
    if isinstance(liq, dict):
        for k, v in liq.items():
            if v is not None:
                m[k] = float(v)

    msg = (
        f"[Liquidity Canary]\n"
        f"Regime: {regime(m)}\n\n"
        f"[Trigger]\n"
        f"{trigger_line}\n\n"
        f"[Momentum]\n"
        f"BTC_R5={r5:.2f}% | VOL={vol_z:.2f}σ | ACC={acc:.2f}\n\n"
        f"[Conclusion]\n"
        f"{conclusion}"
    )

    send(msg)


if __name__ == "__main__":
    run()
