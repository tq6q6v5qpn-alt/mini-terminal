from datetime import datetime,timezone,timedelta
from state import get_num,set_num
from sources import price,funding,oi,klines
from features import candle_features
from analyzer import regime
from telegram import send

KST=timezone(timedelta(hours=9))

def d(k,v): p=get_num(k); set_num(k,v,datetime.now(KST).isoformat()); return 0 if p is None else (v-p)/p*100

def run():
 btc=price('BTCUSDT'); eth=price('ETHUSDT')
 r5,vol,acc=candle_features(klines('BTCUSDT'))
 m={'BTC_R5':r5,'ETH_R5':d('ETH',eth),'BTC_OI':d('OI',oi('BTCUSDT')),'FUND':funding('BTCUSDT'),'VOL':vol,'ACCEL':acc}
 msg=f"Regime: {regime(m)}\nBTC_R5:{r5:.2f}% VOL:{vol:.2f} ACC:{acc:.2f}"
 send(msg)

if __name__=='__main__': run()
