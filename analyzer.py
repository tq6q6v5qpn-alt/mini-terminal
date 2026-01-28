TH={'BTC_R5':0.2,'ETH_R5':0.2,'BTC_OI':0.3,'FUND':0.002,'VOL':0.1,'ACCEL':0.15}

def regime(m):
 if m['BTC_R5']>0.4 and m['BTC_OI']>0.5 and m['FUND']>0 and m['ACCEL']>0: return 'Short-squeeze'
 if m['BTC_R5']<-0.4 and m['BTC_OI']<-0.5 and m['FUND']<0 and m['ACCEL']<0: return 'Long-squeeze'
 if m['BTC_R5']<-0.6 and m['BTC_OI']<-1 and m['VOL']>TH['VOL']: return 'Deleveraging'
 if m['BTC_R5']>0 and m['ETH_R5']>0: return 'Risk-On'
 if m['BTC_R5']<0 and m['ETH_R5']<0: return 'Risk-Off'
 return 'Neutral'
