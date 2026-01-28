import math

def pct(a,b): return 0 if a==0 else (b-a)/a*100

def candle_features(kl):
 c=[float(k[4]) for k in kl]
 if len(c)<3: return 0,0,0
 r5=pct(c[-2],c[-1]); prev=pct(c[-3],c[-2]); acc=r5-prev
 rets=[pct(c[i-1],c[i]) for i in range(1,len(c))]
 m=sum(rets)/len(rets); vol=(sum((x-m)**2 for x in rets)/max(1,len(rets)-1))**0.5
 return r5,vol,acc
