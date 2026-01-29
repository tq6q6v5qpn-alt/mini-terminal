import requests
import time

COINGECKO = "https://api.coingecko.com/api/v3"

def price(sym):
    if sym.upper() != "BTCUSDT":
        return None  # 일단 BTC만

    for _ in range(3):  # 최대 3번 재시도
        r = requests.get(
            f"{COINGECKO}/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd"},
            timeout=10,
        )

        if r.status_code == 429:
            time.sleep(5)
            continue

        r.raise_for_status()
        return float(r.json()["bitcoin"]["usd"])

    return None
def funding(sym):
    return 0.0
