import json, os, time, math
import requests

COINGECKO = "https://api.coingecko.com/api/v3"
CACHE_PATH = "/tmp/cg_btc_1d.json"
CACHE_TTL_SEC = 600  # 10분: 크론이 10분마다 도니 1회 호출로 끝내기

def _get_json(url, params=None, retries=3):
    for i in range(retries):
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            time.sleep(3 + i * 3)
            continue
        r.raise_for_status()
        return r.json()
    # 마지막 시도도 429면 죽지 말고 None
    return None

def _load_cache():
    try:
        if os.path.exists(CACHE_PATH):
            age = time.time() - os.path.getmtime(CACHE_PATH)
            if age < CACHE_TTL_SEC:
                with open(CACHE_PATH, "r") as f:
                    return json.load(f)
    except Exception:
        pass
    return None

def _save_cache(data):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def _market_chart_1d():
    cached = _load_cache()
    if cached:
        return cached
    data = _get_json(
        f"{COINGECKO}/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": "1"},
    )
    if data:
        _save_cache(data)
    return data

def _nearest_value_at(series, target_ms):
    # series: [[ts_ms, value], ...] (오름차순 가정)
    # target_ms 이하에서 가장 가까운 값
    best = None
    for ts, v in series:
        if ts <= target_ms:
            best = v
        else:
            break
    return best

def btc_features():
    """
    return:
      price (float)
      r5 (float)        # 최근 5분 수익률 (예: 0.012 = +1.2%)
      vol_z (float)     # 5분 볼륨의 Z-score (CoinGecko total_volumes 기반)
      acc (float)       # r5의 변화(가속) = r5_now - r5_prev5
    """
    data = _market_chart_1d()
    if not data or "prices" not in data or "total_volumes" not in data:
        return {"price": None, "r5": 0.0, "vol_z": 0.0, "acc": 0.0}

    prices = data["prices"]
    vols = data["total_volumes"]

    # 현재 가격
    now_ts, now_price = prices[-1]
    price_now = float(now_price)

    # R5: 5분 전 가격을 찾아 수익률 계산
    p_5m = _nearest_value_at(prices, now_ts - 5 * 60 * 1000)
    if p_5m is None or p_5m == 0:
        r5 = 0.0
    else:
        r5 = (price_now / float(p_5m)) - 1.0

    # 이전 R5 (10분 전 기준으로 5분 수익률) -> 가속도(ACC)
    p_10m = _nearest_value_at(prices, now_ts - 10 * 60 * 1000)
    p_15m = _nearest_value_at(prices, now_ts - 15 * 60 * 1000)
    if p_10m and p_15m and float(p_15m) != 0:
        r5_prev = (float(p_10m) / float(p_15m)) - 1.0
    else:
        r5_prev = 0.0
    acc = r5 - r5_prev

    # VOL: 5분 볼륨을 “최근 1일의 볼륨 시계열” 대비 Z-score
    # (CoinGecko total_volumes는 완전한 체결 볼륨 캔들은 아니지만, 참여 급증 감지엔 유효)
    v_now = float(vols[-1][1])
    # lookback 볼륨 값들
    v_list = [float(x[1]) for x in vols if x and x[1] is not None]
    if len(v_list) < 30:
        vol_z = 0.0
    else:
        mu = sum(v_list) / len(v_list)
        var = sum((v - mu) ** 2 for v in v_list) / max(1, (len(v_list) - 1))
        sigma = math.sqrt(var) if var > 0 else 0.0
        vol_z = (v_now - mu) / sigma if sigma > 0 else 0.0

    return {"price": price_now, "r5": r5, "vol_z": float(vol_z), "acc": float(acc)}

# 기존 main.py import 호환용 “스텁”들 (에러 방지)
def price(sym):
    f = btc_features()
    return f["price"] if f["price"] is not None else 0.0

def funding(sym):
    return 0.0

def oi(sym):
    return 0.0

def klines(sym):
    return []
