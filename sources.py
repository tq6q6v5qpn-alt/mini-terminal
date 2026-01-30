# sources.py
import requests
from typing import Dict, Optional

COINGECKO = "https://api.coingecko.com/api/v3/simple/price"


def get_crypto_prices_usd() -> Dict[str, Optional[float]]:
    """
    BTC/ETH USD 가격만 가져옴.
    실패하면 None 반환(크론 죽지 않게).
    """
    try:
        params = {"ids": "bitcoin,ethereum", "vs_currencies": "usd"}
        r = requests.get(COINGECKO, params=params, timeout=15)
        r.raise_for_status()
        j = r.json()
        btc = j.get("bitcoin", {}).get("usd")
        eth = j.get("ethereum", {}).get("usd")
        return {"BTC": float(btc) if btc is not None else None,
                "ETH": float(eth) if eth is not None else None}
    except Exception:
        return {"BTC": None, "ETH": None}
