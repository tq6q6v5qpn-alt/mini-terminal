import sqlite3
from typing import Optional

_CONN=sqlite3.connect('state.db')
_CUR=_CONN.cursor()
_CUR.execute('CREATE TABLE IF NOT EXISTS kv_num (k TEXT PRIMARY KEY, v REAL, ts TEXT)')
_CUR.execute('CREATE TABLE IF NOT EXISTS kv_text (k TEXT PRIMARY KEY, v TEXT, ts TEXT)')
_CONN.commit()

def get_num(k:str)->Optional[float]:
 _CUR.execute('SELECT v FROM kv_num WHERE k=?',(k,)); r=_CUR.fetchone(); return float(r[0]) if r else None

def set_num(k:str,v:float,ts:str):
 _CUR.execute('INSERT INTO kv_num VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, ts=excluded.ts',(k,v,ts)); _CONN.commit()

def get_text(k:str)->Optional[str]:
 _CUR.execute('SELECT v FROM kv_text WHERE k=?',(k,)); r=_CUR.fetchone(); return r[0] if r else None

def set_text(k:str,v:str,ts:str):
 _CUR.execute('INSERT INTO kv_text VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, ts=excluded.ts',(k,v,ts)); _CONN.commit()
