import requests

COINGECKO = "https://api.coingecko.com/api/v3"

def price(sym):
    if sym.upper() != "BTCUSDT":
        raise ValueError("Only BTCUSDT supported")
    r = requests.get(
        f"{COINGECKO}/simple/price",
        params={"ids": "bitcoin", "vs_currencies": "usd"},
        timeout=10,
    )
    r.raise_for_status()
    return float(r.json()["bitcoin"]["usd"])

def funding(sym):
    return 0.0

def oi(sym):
    return 0.0

def klines(sym):
    return []
