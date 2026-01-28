import requests

def get(url,p=None): r=requests.get(url,params=p,timeout=15); r.raise_for_status(); return r.json()

def price(sym): return float(get('https://api.binance.com/api/v3/ticker/price',{'symbol':sym})['price'])

def funding(sym): return float(get('https://fapi.binance.com/fapi/v1/premiumIndex',{'symbol':sym})['lastFundingRate'])

def oi(sym): return float(get('https://fapi.binance.com/fapi/v1/openInterest',{'symbol':sym})['openInterest'])

def klines(sym): return get('https://api.binance.com/api/v3/klines',{'symbol':sym,'interval':'5m','limit':30})
