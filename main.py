import time
import requests
import pandas as pd
from datetime import datetime
import pytz

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8785813821:AAGR2kLZg6EKepSEtW5NoDs66tRqUaPIEP8"

TELEGRAM_CHAT_ID = "-1004458934308"

PROXIES = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}

# Sirf inhi specific pairs par nazar rakhega
WATCHLIST = [
    'BTCUSDT', 
    'ETHUSDT', 
    'XRPUSDT', 
    'PAXGUSDT', # XAU (Gold equivalent on Binance)
    'ZECUSDT'
]

COOLDOWN_SECONDS = 10800  # 3 Hours
MIN_AI_SCORE = 80

sent_history = {}
active_trades = {}  # Live price tracking for TP/SL alerts

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_pakistan_time():
    """Pakistan Local Time Return Karta Hai"""
    pkt = pytz.timezone('Asia/Karachi')
    now = datetime.now(pkt)
    return now.strftime("%d-%m-%y  - %I:%M%p").lower()

def fetch_klines(symbol, timeframe, limit=100):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
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
    
    if rsi.iloc[-1] < 38: bull += 50
    elif rsi.iloc[-1] > 62: bear += 50
    
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
    except Exception:
        return False

# ==========================================
# TP / SL RESULT CHECKER
# ==========================================
def check_active_trade_results():
    """Send kiye hue trades ki live updates check karta hai (TP1, TP2, SL)"""
    for symbol, trade in list(active_trades.items()):
        df = fetch_klines(symbol, '1m', limit=1)
        if df is None: continue
        
        current_price = df['close'].iloc[-1]
        pair_clean = symbol.replace('USDT', '')
        if pair_clean == 'PAXG': pair_clean = 'XAU'
        
        direction = trade['direction']
        
        if direction == 'LONG':
            if current_price >= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(f"🎯 **RESULT ALERT** 🎯\n\n**{pair_clean} / LONG**\n✅ **TP2 HIT:** `{trade['tp2']}` 🔥\n⏰ Time: {get_pakistan_time()}")
                trade['tp2_hit'] = True
                del active_trades[symbol]
            elif current_price >= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(f"🎯 **RESULT ALERT** 🎯\n\n**{pair_clean} / LONG**\n✅ **TP1 HIT:** `{trade['tp1']}` 🚀\n⏰ Time: {get_pakistan_time()}")
                trade['tp1_hit'] = True
            elif current_price <= trade['sl']:
                send_telegram_msg(f"🛑 **RESULT ALERT** 🛑\n\n**{pair_clean} / LONG**\n❌ **STOP LOSS HIT:** `{trade['sl']}`\n⏰ Time: {get_pakistan_time()}")
                del active_trades[symbol]
                
        elif direction == 'SHORT':
            if current_price <= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(f"🎯 **RESULT ALERT** 🎯\n\n**{pair_clean} / SHORT**\n✅ **TP2 HIT:** `{trade['tp2']}` 🔥\n⏰ Time: {get_pakistan_time()}")
                trade['tp2_hit'] = True
                del active_trades[symbol]
            elif current_price <= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(f"🎯 **RESULT ALERT** 🎯\n\n**{pair_clean} / SHORT**\n✅ **TP1 HIT:** `{trade['tp1']}` 🚀\n⏰ Time: {get_pakistan_time()}")
                trade['tp1_hit'] = True
            elif current_price >= trade['sl']:
                send_telegram_msg(f"🛑 **RESULT ALERT** 🛑\n\n**{pair_clean} / SHORT**\n❌ **STOP LOSS HIT:** `{trade['sl']}`\n⏰ Time: {get_pakistan_time()}")
                del active_trades[symbol]

# ==========================================
# SIGNAL GENERATION ENGINE
# ==========================================
def analyze_and_build_signal(symbol):
    df_15m = fetch_klines(symbol, '15m')
    df_1h = fetch_klines(symbol, '1h')
    
    score_15, trend_15 = analyze_tf(df_15m)
    score_1h, trend_1h = analyze_tf(df_1h)
    
    if trend_15 == "NEUTRAL" or trend_15 != trend_1h:
        return None
        
    final_score = int((score_15 * 0.6) + (score_1h * 0.4))
    if final_score < MIN_AI_SCORE:
        return None
        
    price = df_15m['close'].iloc[-1]
    
    timeframe_type = "15m Scalp Trade" if score_15 >= score_1h else "1h Intra-Day Trade"
    
    if trend_15 == "LONG":
        sl = round(price * 0.985, 2)
        tp1 = round(price * 1.015, 2)
        tp2 = round(price * 1.030, 2)
    else:
        sl = round(price * 1.015, 2)
        tp1 = round(price * 0.985, 2)
        tp2 = round(price * 0.970, 2)
        
    pair_clean = symbol.replace('USDT', '')
    if pair_clean == 'PAXG': pair_clean = 'XAU'
    
    pk_time = get_pakistan_time()
    
    # Exact Notebook Clean Format
    msg = (
        f"**{pair_clean} / {trend_15}**   `{pk_time}`\n\n"
        f"**Ent** = `{price}`\n\n"
        f"**SL** = `{sl}`\n\n"
        f"**TP** = `{tp1}`\n\n"
        f"**TP** = `{tp2}`\n\n"
        f"**Detail**\n"
        f"⏳ Timeframe: {timeframe_type}"
    )
    
    trade_data = {
        'direction': trend_15,
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
        # Step 1: Check existing trades for TP/SL hits
        check_active_trade_results()
        
        # Step 2: Scan watchlist for new signals
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
            except Exception as e:
                print(f"[!] Error on {symbol}: {e}")
            time.sleep(1)
            
        time.sleep(300) # 5 Min Loop

if __name__ == "__main__":
    main()
