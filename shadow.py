"""
Shadow tracker: AI ne jo signals roke, unka chupke se record rakhta hai.
- Signal channel mein kuch nahi jata, sirf admin ko roz raat 11 baje ek report.
- Apni alag file (shadow_state.json) use karta hai, bot ki bot_state.json ko nahi chhuta.
- main.py se 3 jagah judta hai: import, AI-veto wali jagah, aur main_loop.
"""
import os
import json
import time
import threading
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
import pandas as pd

log = logging.getLogger("shadow")

# main.py ke saath SYNC rakho
MIN_FINAL_SCORE = 72
ATR_PERIOD      = 14
SL_ATR_MULT     = 1.5
MIN_SL_PCT      = 0.006
TP1_R           = 1.2
TP2_R           = 2.5
EXPIRY_HOURS    = 48
COOLDOWN_SEC    = 7200
REPORT_HOUR     = 23          # Pakistan time

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN = os.environ.get("TELEGRAM_ADMIN_ID", "xxxx")
FILE  = os.environ.get(
    "SHADOW_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "shadow_state.json"),
)

_lock = threading.RLock()
_state = {"open": {}, "closed": [], "last_close": {}, "seen": 0, "qualified": 0,
          "last_report_date": None}
_loaded = False
PK = ZoneInfo("Asia/Karachi")


# ---------- helpers ----------
def _pk_now_str():
    return datetime.now(PK).strftime("%d-%b-%Y | %I:%M %p")

def _pk_from_ms(ms):
    return datetime.fromtimestamp(int(ms) / 1000, PK).strftime("%d-%b-%Y | %I:%M %p")

def _save():
    try:
        with _lock:
            payload = json.dumps(_state, default=str)
        tmp = FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(payload)
        os.replace(tmp, FILE)
    except Exception as e:
        log.error(f"[shadow] save error: {e}")

def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if os.path.exists(FILE):
            with open(FILE) as f:
                data = json.load(f)
            with _lock:
                _state.update(data)
            log.info(f"👻 Shadow state loaded | open: {len(_state['open'])} | closed: {len(_state['closed'])}")
    except Exception as e:
        log.error(f"[shadow] load error: {e}")

def _send_admin(text):
    if ADMIN == "xxxx" or not TOKEN:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                      json={"chat_id": ADMIN, "text": text}, timeout=30)
    except Exception as e:
        log.error(f"[shadow] telegram error: {e}")

def _live_price(symbol):
    try:
        r = requests.get(f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}", timeout=10)
        return float(r.json()["price"])
    except Exception:
        return None

def _klines_since(symbol, start_ms):
    """start_ms ke baad ki sirf CLOSED 1m candles."""
    try:
        url = (f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}"
               f"&interval=1m&startTime={int(start_ms)}&limit=1000")
        data = requests.get(url, timeout=10).json()
        if isinstance(data, dict):
            return None
        if not data:
            return pd.DataFrame(columns=["time", "high", "low"])
        df = pd.DataFrame(data).iloc[:, [0, 2, 3, 6]]
        df.columns = ["time", "high", "low", "close_time"]
        df["time"] = df["time"].astype("int64")
        df["close_time"] = df["close_time"].astype("int64")
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df[df["close_time"] < int(time.time() * 1000)].reset_index(drop=True)
    except Exception as e:
        log.error(f"[shadow] klines {symbol}: {e}")
        return None


# ---------- 1) AI veto par record ----------
def on_veto(symbol, trend, tech_score, df_1h):
    """main.py ke AI-veto wali jagah se bulao. Kabhi bot ko crash nahi karta."""
    try:
        _load()
        with _lock:
            _state["seen"] += 1

        # Agar AI neutral hota to kya score banta? (ai_prob 0.5 = 15 points)
        would_be = tech_score * 0.70 + 50 * 0.30
        if would_be < MIN_FINAL_SCORE:
            _save()
            return

        with _lock:
            _state["qualified"] += 1
            if symbol in _state["open"]:
                return
            if time.time() - _state["last_close"].get(symbol, 0) < COOLDOWN_SEC:
                return

        price = _live_price(symbol)
        if price is None:
            return
        high, low, close = df_1h["high"], df_1h["low"], df_1h["close"]
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(ATR_PERIOD).mean().iloc[-1]
        if pd.isna(atr) or atr <= 0:
            return

        risk = max(SL_ATR_MULT * atr, price * MIN_SL_PCT)
        sign = 1 if trend == "LONG" else -1
        now_ms = int(time.time() * 1000)
        trade = {
            "direction": trend, "entry": price,
            "sl": price - sign * risk, "sl_orig": price - sign * risk,
            "tp1": price + sign * risk * TP1_R, "tp2": price + sign * risk * TP2_R,
            "tp1_hit": False, "tp1_time": None,
            "signal_time": _pk_now_str(), "signal_ts_ms": now_ms,
            "last_checked_ms": (now_ms // 60000 + 1) * 60000,
            "score": round(would_be, 1),
        }
        with _lock:
            _state["open"][symbol] = trade
        _save()
        log.info(f"👻 Shadow recorded: {symbol} {trend} (AI roka, score {trade['score']})")
    except Exception as e:
        log.error(f"[shadow] on_veto: {e}")


# ---------- 2) candles process (bot jaisa hi logic) ----------
def process(trade, df):
    """Returns (result, close_time_str) ya None. Result: SL / BE / TP2 / EXPIRED."""
    is_long = trade["direction"] == "LONG"
    for _, c in df.iterrows():
        hi, lo = c["high"], c["low"]
        ht = _pk_from_ms(c["time"])
        sl_hit  = lo <= trade["sl"]  if is_long else hi >= trade["sl"]
        tp1_hit = hi >= trade["tp1"] if is_long else lo <= trade["tp1"]
        tp2_hit = hi >= trade["tp2"] if is_long else lo <= trade["tp2"]
        if not trade["tp1_hit"]:
            if sl_hit:
                return "SL", ht
            if tp1_hit:
                trade["tp1_hit"] = True
                trade["tp1_time"] = ht
                trade["sl"] = trade["entry"]
                if tp2_hit:
                    return "TP2", ht
        else:
            if sl_hit:
                return "BE", ht
            if tp2_hit:
                return "TP2", ht
    if (time.time() * 1000 - trade["signal_ts_ms"]) / 3600000 > EXPIRY_HOURS:
        return "EXPIRED", _pk_now_str()
    return None


def _check_open():
    with _lock:
        symbols = list(_state["open"].keys())
    for sym in symbols:
        with _lock:
            trade = _state["open"].get(sym)
            if not trade:
                continue
            start = int(trade.get("last_checked_ms") or trade["signal_ts_ms"])
        df = _klines_since(sym, start)
        if df is None:
            continue
        with _lock:
            trade = _state["open"].get(sym)
            if not trade:
                continue
            res = process(trade, df)
            if res:
                result, ct = res
                rec = dict(trade)
                rec.update(symbol=sym, result=result, close_time=ct, closed_ts=time.time())
                _state["closed"].append(rec)
                _state["closed"] = _state["closed"][-500:]
                _state["last_close"][sym] = time.time()
                _state["open"].pop(sym, None)
                log.info(f"👻 Shadow closed: {sym} {trade['direction']} -> {result}")
            elif not df.empty:
                trade["last_checked_ms"] = int(df["time"].iloc[-1]) + 60000
        _save()


# ---------- 3) report ----------
R_VALUE = {"TP2": TP2_R, "BE": 0.0, "SL": -1.0, "EXPIRED": 0.0}

def _summ(rows):
    sl = sum(1 for r in rows if r["result"] == "SL")
    be = sum(1 for r in rows if r["result"] == "BE")
    tp2 = sum(1 for r in rows if r["result"] == "TP2")
    ex = sum(1 for r in rows if r["result"] == "EXPIRED")
    net = sum(R_VALUE.get(r["result"], 0) for r in rows)
    return sl, be, tp2, ex, net

def build_report():
    today = datetime.now(PK).strftime("%d-%b-%Y")
    with _lock:
        closed = list(_state["closed"])
        open_n = len(_state["open"])
        seen, qual = _state["seen"], _state["qualified"]
    todays = [r for r in closed if str(r.get("close_time", "")).startswith(today)]

    def block(title, rows):
        sl, be, tp2, ex, net = _summ(rows)
        return (f"{title}: {len(rows)} band\n"
                f"   SL: {sl} | Breakeven (TP1 ke baad): {be} | TP2: {tp2} | Expire: {ex}\n"
                f"   Net: {net:+.1f}R")

    msg = (f"🕵️ AI VETO REPORT — {today}\n"
           f"(Ye signal AI ne roke the. Channel mein nahi gaye.)\n"
           f"══════════════════\n"
           f"AI ne ab tak roke: {seen} baar\n"
           f"Un mein score pass karne wale: {qual}\n"
           f"Abhi khule: {open_n}\n\n"
           + block("Aaj", todays) + "\n\n" + block("Ab tak (kul)", closed))

    _, _, _, _, net_all = _summ(closed)
    if len(closed) >= 20:
        msg += ("\n\n➡️ Net negative: AI ne sahi roka." if net_all < 0
                else "\n\n➡️ Net positive: AI achhe signal rok raha hai, veto dhila karne par sochna.")
    else:
        msg += f"\n\n⏳ Abhi sirf {len(closed)} band trade, faisle ke liye kam az kam 20 chahiye."

    if todays:
        msg += "\n\n📋 Aaj band hue:\n"
        for i, r in enumerate(todays[:15], 1):
            d = "🟢" if r["direction"] == "LONG" else "🔴"
            msg += f"{i}. {d} {r['symbol'].replace('USDT','')} | {r['result']} | Entry {r['signal_time']} | Band {r['close_time']}\n"
    return msg


# ---------- 4) main_loop se bulao ----------
def tick():
    """Har loop mein bulao: khule shadow trades check + roz raat 11 baje report."""
    try:
        _load()
        _check_open()
        now = datetime.now(PK)
        today = now.strftime("%d-%b-%Y")
        with _lock:
            due = now.hour == REPORT_HOUR and _state["last_report_date"] != today
        if due:
            _send_admin(build_report())
            with _lock:
                _state["last_report_date"] = today
            _save()
    except Exception as e:
        log.error(f"[shadow] tick: {e}")
