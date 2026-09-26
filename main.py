import os
import time
import requests
import pandas as pd
from datetime import datetime
import pytz
import threading
from flask import Flask

# ==========================================
# 0. RENDER PORT BINDING (Flask Web Server)
# ==========================================

app = Flask(__name__)

@app.route('/')
def home():
    return "Crypto & Gold Signal Bot is Active 24/7 on Render!"

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8785813821:AAGR2kLZg6EKepSEtW5NoDs66tRqUaPIEP8"
TELEGRAM_CHAT_ID = "-1004458934308"

PROXIES = None

WATCHLIST = [
    # Top Crypto
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'SUIUSDT',
    'NEARUSDT', 'APTUSDT', 'LTCUSDT', 'DOTUSDT', 'BCHUSDT',

    # Specific Volatile & Trending Coins
    'ZECUSDT', 'PEPEUSDT', 'SHIBUSDT', 'FETUSDT',
    'RENDERUSDT', 'INJUSDT', 'TIAUSDT', 'TAOUSDT', 'SEIUSDT',

    # Gold
    'PAXGUSDT', # Spot Gold
    'XAUUSDT'   # Futures Gold
]

COOLDOWN_SECONDS = 10800  # 3 Hours
MIN_AI_SCORE = 10

sent_history = {}
active_trades = {}  # Live price tracking for TP/SL alerts

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_pakistan_time():
    """Pakistan Local Time Return Karta Hai"""
    pkt = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt)
    return now.strftime("%d-%b-%Y | %I:%M %p")

def fetch_klines(symbol, timeframe, limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
        
        if isinstance(data, dict):
            return None
            
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        return df
    except Exception:
        return None

# ==========================================
# TECHNICAL ANALYSIS & SCORING
# ==========================================
def analyze_tf(df):
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"
    
    close = df['close']
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    
    price = close.iloc[-1]
    bull, bear = 0, 0
    
    if rsi.iloc[-1] < 50: bull += 50
    elif rsi.iloc[-1] > 50: bear += 50
    
    if price > ema20.iloc[-1] > sma50.iloc[-1]: bull += 50
    elif price < ema20.iloc[-1] < sma50.iloc[-1]: bear += 50
    
    if bull > bear: return bull, "LONG"
    elif bear > bull: return bear, "SHORT"
    return 0, "NEUTRAL"

def send_telegram_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Telegram Dispatch Failed: {e}")
        return False

# ==========================================
# TP / SL RESULT CHECKER
# ==========================================
def check_active_trade_results():
    for symbol, trade in list(active_trades.items()):
        df = fetch_klines(symbol, '1m', limit=1)
        if df is None: continue
        
        current_price = df['close'].iloc[-1]
        pair_clean = symbol.replace('USDT', '')
        if pair_clean in ['PAXG', 'XAU']: pair_clean = 'XAU / GOLD'
        
        direction = trade['direction']
        
        if direction == 'LONG':
            if current_price >= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(
                    f"🔥 **TARGET 2 HIT (FULL TP)** 🔥\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **LONG** 🟢\n"
                    f"✅ **TP2 Price:** `{trade['tp2']}`\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                trade['tp2_hit'] = True
                del active_trades[symbol]
            elif current_price >= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(
                    f"🚀 **TARGET 1 HIT** 🚀\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **LONG** 🟢\n"
                    f"✅ **TP1 Price:** `{trade['tp1']}`\n"
                    f"💡 *Lock profits or set SL to Entry!*\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                trade['tp1_hit'] = True
            elif current_price <= trade['sl']:
                send_telegram_msg(
                    f"🛑 **STOP LOSS HIT** 🛑\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **LONG** 🟢\n"
                    f"❌ **SL Price:** `{trade['sl']}`\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                del active_trades[symbol]
                
        elif direction == 'SHORT':
            if current_price <= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(
                    f"🔥 **TARGET 2 HIT (FULL TP)** 🔥\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **SHORT** 🔴\n"
                    f"✅ **TP2 Price:** `{trade['tp2']}`\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                trade['tp2_hit'] = True
                del active_trades[symbol]
            elif current_price <= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(
                    f"🚀 **TARGET 1 HIT** 🚀\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **SHORT** 🔴\n"
                    f"✅ **TP1 Price:** `{trade['tp1']}`\n"
                    f"💡 *Lock profits or set SL to Entry!*\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                trade['tp1_hit'] = True
            elif current_price >= trade['sl']:
                send_telegram_msg(
                    f"🛑 **STOP LOSS HIT** 🛑\n\n"
                    f"📌 **Pair:** `{pair_clean}` | **SHORT** 🔴\n"
                    f"❌ **SL Price:** `{trade['sl']}`\n"
                    f"⏰ **Time:** `{get_pakistan_time()}`"
                )
                del active_trades[symbol]

# ==========================================
# SIGNAL GENERATION ENGINE
# ==========================================
def analyze_and_build_signal(symbol):
    df_15m = fetch_klines(symbol, '15m')
    df_1h = fetch_klines(symbol, '1h')
    
    if df_15m is None or df_1h is None:
        return None

    score_15, trend_15 = analyze_tf(df_15m)
    score_1h, trend_1h = analyze_tf(df_1h)
    print(f"🔍 Scanning {symbol}... 15m Score: {score_15}, 1h Score: {score_1h}")

    active_trend = trend_15 if trend_15 != "NEUTRAL" else trend_1h
    if active_trend == "NEUTRAL":
        return None
        
    final_score = max(score_15, score_1h)
    if final_score < MIN_AI_SCORE:
        return None
        
    price = df_15m['close'].iloc[-1]
    
    timeframe_type = "⚡ 15m Scalp Trade" if score_15 >= score_1h else "📈 1h Intra-Day Trade"
    
    if active_trend == "LONG":
        badge = "🟢 **BUY / LONG SIGNAL** 🟢"
        sl = round(price * 0.985, 2)
        tp1 = round(price * 1.015, 2)
        tp2 = round(price * 1.030, 2)
    else:
        badge = "🔴 **SELL / SHORT SIGNAL** 🔴"
        sl = round(price * 1.015, 2)
        tp1 = round(price * 0.985, 2)
        tp2 = round(price * 0.970, 2)
        
    pair_clean = symbol.replace('USDT', '')
    if pair_clean in ['PAXG', 'XAU']: pair_clean = 'XAU / GOLD'
    
    pk_time = get_pakistan_time()
    
    msg = (
        f"{badge}\n"
        f"═══════════════════\n"
        f"🪙 **ASSET:** `{pair_clean}`\n"
        f"⏰ **TIME:** `{pk_time}`\n"
        f"═══════════════════\n\n"
        f"💵 **ENTRY:** `{price}`\n\n"
        f"🎯 **TP 1:** `{tp1}`\n"
        f"🎯 **TP 2:** `{tp2}`\n\n"
        f"🛑 **STOP LOSS:** `{sl}`\n\n"
        f"═══════════════════\n"
        f"📊 **SETUP:** {timeframe_type}"
    )
    
    trade_data = {
        'direction': active_trend,
        'entry': price,
        'sl': sl,
        'tp1': tp1,
        'tp2': tp2,
        'tp1_hit': False,
        'tp2_hit': False
    }
    
    return msg, pair_clean, trade_data

# ==========================================
# MAIN LOOP
# ==========================================
def main():
    print("🚀 Custom Asset Signal & Result Tracker Started...")

    while True:
        check_active_trade_results()
        
        for symbol in WATCHLIST:
            try:
                res = analyze_and_build_signal(symbol)
                if res:
                    msg, coin_name, trade_data = res
                    curr_time = time.time()
                    
                    if coin_name not in sent_history or (curr_time - sent_history[coin_name]) > COOLDOWN_SECONDS:
                        if send_telegram_msg(msg):
                            sent_history[coin_name] = curr_time
                            active_trades[symbol] = trade_data
                            print(f"✅ Signal Sent for {coin_name}")
                else:
                    print(f"⏩ {symbol} scanned. Waiting for strong setup...")
            except Exception as e:
                print(f"[!] Error on {symbol}: {e}")
            time.sleep(1)
            
        print("⏳ Scan cycle complete. Sleeping 3 minutes...\n")
        time.sleep(180)

def start_bot_background():
    print("🚀 Bot Scanner Loop starting now via Gunicorn...")
    try:
        main()
    except Exception as e:
        print(f"❌ Error in main loop: {e}")

# MAIN THREAD: Pehle saare functions (main wagera) load ho gaye, ab thread start hogi
threading.Thread(target=start_bot_background, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
