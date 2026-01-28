import os,requests,hashlib
from state import get_text,set_text
from datetime import datetime

def send(msg):
 h=hashlib.md5(msg.encode()).hexdigest()
 if get_text('LAST')==h: return
 url=f"https://api.telegram.org/bot{os.getenv('TG_BOT_TOKEN')}/sendMessage"
 requests.post(url,json={'chat_id':os.getenv('TG_CHAT_ID'),'text':msg})
 set_text('LAST',h,datetime.now().isoformat())
