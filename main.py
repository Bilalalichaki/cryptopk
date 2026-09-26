import os
import time
import requests
import pandas as pd
from datetime import datetime
import pytz
import threading
import logging
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8785813821:AAHjp4SvcI2Dg1VAgqgB39OTI50EMwgSAwE")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "-1004458934308")

if TELEGRAM_BOT_TOKEN == "8785813821:AAHjp4SvcI2Dg1VAgqgB39OTI50EMwgSAwE" or TELEGRAM_CHAT_ID == "-1004458934308":
    raise SystemExit("❌ Env vars set karo: TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID")

PROXIES = None

WATCHLIST = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'SUIUSDT',
    'NEARUSDT', 'APTUSDT', 'LTCUSDT', 'DOTUSDT', 'BCHUSDT',
    'ZECUSDT', 'PEPEUSDT', 'SHIBUSDT', 'FETUSDT',
    'RENDERUSDT', 'INJUSDT', 'TIAUSDT', 'TAOUSDT', 'SEIUSDT',
    'PAXGUSDT',
]

FUTURES_WATCHLIST = ['XAUUSDT']

COOLDOWN_SECONDS = 10800
MIN_AI_SCORE     = 60
SCAN_INTERVAL    = 180

sent_history  = {}
active_trades = {}
state_lock    = threading.Lock()

def get_pakistan_time():
    pkt = pytz.timezone('Asia/Karachi')
    return datetime.now(pkt).strftime("%d-%b-%Y | %I:%M %p")

def round_price(p):
    if p >= 1000:     return round(p, 2)
    elif p >= 1:      return round(p, 4)
    elif p >= 0.01:   return round(p, 5)
    elif p >= 0.0001: return round(p, 6)
    else:             return round(p, 8)

def fetch_klines(symbol, timeframe, limit=100, futures=False):
    try:
        if futures:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        else:
            url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
        if isinstance(data, dict) or not data:
            logger.warning(f"[fetch_klines] Bad response {symbol}: {str(data)[:150]}")
            return None
        df = pd.DataFrame(data, columns=[
            'time','open','high','low','close','volume',
            '_1','_2','_3','_4','_5','_6'
        ])
        for c in ['open','high','low','close','volume']:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        logger.error(f"[fetch_klines] {symbol} {timeframe}: {e}")
        return None

def analyze_tf(df):
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"
    close = df['close']
    delta = close.diff()
    gain  = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    price = close.iloc[-1]
    bull, bear = 0, 0
    if rsi.iloc[-1] < 40:    bull += 50
    elif rsi.iloc[-1] < 50:  bull += 30
    elif rsi.iloc[-1] > 60:  bear += 50
    elif rsi.iloc[-1] > 50:  bear += 30
    if price > ema20.iloc[-1] > sma50.iloc[-1]:    bull += 50
    elif price > ema20.iloc[-1]:                    bull += 25
    elif price < ema20.iloc[-1] < sma50.iloc[-1]:  bear += 50
    elif price < ema20.iloc[-1]:                    bear += 25
    if bull > bear:   return bull, "LONG"
    elif bear > bull: return bear, "SHORT"
    return 0, "NEUTRAL"

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        if res.status_code != 200:
            logger.error(f"[Telegram] {res.status_code}: {res.text[:200]}")
            return False
        return True
    except Exception as e:
        logger.error(f"[Telegram] Exception: {e}")
        return False

def check_active_trade_results():
    with state_lock:
        symbols = list(active_trades.keys())
    for symbol in symbols:
        trade = active_trades.get(symbol)
        if trade is None: continue
        is_futures = symbol in FUTURES_WATCHLIST
        df = fetch_klines(symbol, '1m', limit=2, futures=is_futures)
        if df is None: continue
        price = df['close'].iloc[-1]
        pair = symbol.replace('USDT', '')
        if pair in ['PAXG', 'XAU']: pair = 'XAU / GOLD'
        d = trade['direction']
        remove = False
        if d == 'LONG':
            if price >= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(f"🔥 *TARGET 2 HIT (FULL TP)* 🔥\n\n📌 *Pair:* `{pair}` | *LONG* 🟢\n✅ *TP2:* `{trade['tp2']}`\n⏰ *Time:* `{get_pakistan_time()}`")
                trade['tp2_hit'] = True; remove = True
            elif price >= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(f"🚀 *TARGET 1 HIT* 🚀\n\n📌 *Pair:* `{pair}` | *LONG* 🟢\n✅ *TP1:* `{trade['tp1']}`\n💡 *Lock profits / move SL to entry*\n⏰ *Time:* `{get_pakistan_time()}`")
                trade['tp1_hit'] = True
            elif price <= trade['sl']:
                send_telegram_msg(f"🛑 *STOP LOSS HIT* 🛑\n\n📌 *Pair:* `{pair}` | *LONG* 🟢\n❌ *SL:* `{trade['sl']}`\n⏰ *Time:* `{get_pakistan_time()}`")
                remove = True
        elif d == 'SHORT':
            if price <= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(f"🔥 *TARGET 2 HIT (FULL TP)* 🔥\n\n📌 *Pair:* `{pair}` | *SHORT* 🔴\n✅ *TP2:* `{trade['tp2']}`\n⏰ *Time:* `{get_pakistan_time()}`")
                trade['tp2_hit'] = True; remove = True
            elif price <= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(f"🚀 *TARGET 1 HIT* 🚀\n\n📌 *Pair:* `{pair}` | *SHORT* 🔴\n✅ *TP1:* `{trade['tp1']}`\n💡 *Lock profits / move SL to entry*\n⏰ *Time:* `{get_pakistan_time()}`")
                trade['tp1_hit'] = True
            elif price >= trade['sl']:
                send_telegram_msg(f"🛑 *STOP LOSS HIT* 🛑\n\n📌 *Pair:* `{pair}` | *SHORT* 🔴\n❌ *SL:* `{trade['sl']}`\n⏰ *Time:* `{get_pakistan_time()}`")
                remove = True
        if remove:
            with state_lock:
                active_trades.pop(symbol, None)

def analyze_and_build_signal(symbol, is_futures=False):
    df_15 = fetch_klines(symbol, '15m', futures=is_futures)
    df_1h = fetch_klines(symbol, '1h',  futures=is_futures)
    if df_15 is None or df_1h is None: return None
    s15, t15 = analyze_tf(df_15)
    s1h, t1h = analyze_tf(df_1h)
    logger.info(f"🔍 {symbol} | 15m: {s15}/{t15} | 1h: {s1h}/{t1h}")
    if t15 == t1h and t15 != "NEUTRAL":
        trend = t15; score = min(s15, s1h); label = "🔥 Multi-TF Aligned"
    else:
        trend = t15 if s15 >= s1h else t1h
        score = max(s15, s1h)
        if trend == "NEUTRAL": return None
        label = "⚡ 15m Scalp" if s15 >= s1h else "📈 1h Intra-Day"
    if score < MIN_AI_SCORE: return None
    price = df_15['close'].iloc[-1]
    if trend == "LONG":
        badge = "🟢 *BUY / LONG SIGNAL* 🟢"
        sl = round_price(price * 0.985); tp1 = round_price(price * 1.015); tp2 = round_price(price * 1.030)
    else:
        badge = "🔴 *SELL / SHORT SIGNAL* 🔴"
        sl = round_price(price * 1.015); tp1 = round_price(price * 0.985); tp2 = round_price(price * 0.970)
    pair = symbol.replace('USDT', '')
    if pair in ['PAXG', 'XAU']: pair = 'XAU / GOLD'
    msg = (
        f"{badge}\n═══════════════════\n"
        f"🪙 *ASSET:* `{pair}`\n"
        f"⏰ *TIME:* `{get_pakistan_time()}`\n"
        f"📊 *SCORE:* `{score}/100`\n"
        f"═══════════════════\n\n"
        f"💵 *ENTRY:* `{round_price(price)}`\n\n"
        f"🎯 *TP 1:* `{tp1}`\n🎯 *TP 2:* `{tp2}`\n\n"
        f"🛑 *STOP LOSS:* `{sl}`\n\n"
        f"═══════════════════\n📈 *SETUP:* {label}"
    )
    return msg, pair, {
        'direction': trend, 'entry': price,
        'sl': sl, 'tp1': tp1, 'tp2': tp2,
        'tp1_hit': False, 'tp2_hit': False
    }

def main_loop():
    logger.info("🚀 Signal Bot Started...")
    while True:
        try:
            check_active_trade_results()
            for symbol in WATCHLIST:
                try:
                    res = analyze_and_build_signal(symbol, is_futures=False)
                    if res:
                        msg, coin, data = res
                        now = time.time()
                        if (now - sent_history.get(coin, 0)) > COOLDOWN_SECONDS:
                            if send_telegram_msg(msg):
                                sent_history[coin] = now
                                with state_lock: active_trades[symbol] = data
                                logger.info(f"✅ Signal sent: {coin}")
                except Exception as e:
                    logger.error(f"[Scan] {symbol}: {e}")
            for symbol in FUTURES_WATCHLIST:
                try:
                    res = analyze_and_build_signal(symbol, is_futures=True)
                    if res:
                        msg, coin, data = res
                        now = time.time()
                        if (now - sent_history.get(coin, 0)) > COOLDOWN_SECONDS:
                            if send_telegram_msg(msg):
                                sent_history[coin] = now
                                with state_lock: active_trades[symbol] = data
                                logger.info(f"✅ Signal sent: {coin}")
                except Exception as e:
                    logger.error(f"[Scan-Futures] {symbol}: {e}")
            logger.info(f"⏳ Cycle done. Active: {len(active_trades)} | Sleep {SCAN_INTERVAL}s")
            time.sleep(SCAN_INTERVAL)
        except Exception as e:
            logger.error(f"[MainLoop] {e}")
            time.sleep(60)

@app.route('/')
def health():
    return "Bot is running 24/7!", 200

@app.route('/status')
def status():
    return {
        "status": "alive",
        "active_trades": len(active_trades),
        "tracked_coins": len(sent_history),
        "time": get_pakistan_time()
    }, 200

_scanner_started = False
_scanner_lock = threading.Lock()

def start_scanner_once():
    global _scanner_started
    with _scanner_lock:
        if not _scanner_started:
            threading.Thread(target=main_loop, daemon=True).start()
            _scanner_started = True
            logger.info("🔧 Scanner thread launched.")

start_scanner_once()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)