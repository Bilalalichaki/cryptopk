import time
import requests
import pandas as pd
import numpy as np

# ==========================================
# CONFIGURATION & SETTINGS
# ==========================================
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"

# Tor SOCKS5 Proxy Settings
PROXIES = {
    'http': 'socks5h://127.0.0.1:9050',
    'https': 'socks5h://127.0.0.1:9050'
}

# Rotation & Anti-Spam Settings
BATCH_SIZE = 50          # Har cycle me kitne naye coins scan karne hain
SCAN_OFFSET = 0         # Market rotation index tracker
COOLDOWN_SECONDS = 10800 # 3 Hours Cooldown per coin (3600s = 1 hr, 10800s = 3 hrs)
MIN_AI_SCORE = 80       # Strict Win Probability Threshold (80%+)

# Ignore Stablecoins & Fiat
EXCLUDED_PAIRS = {'USDC', 'FDUSD', 'RLUSD', 'BUSD', 'DAI', 'USDT', 'EUR', 'AEUR', 'PAX', 'TUSD', 'USD1', 'U'}

# Historical Cooldown Tracker
sent_history = {}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_all_usdt_pairs():
    """Binance se tamam valid USDT pairs fetch karke volume ke mutabiq sort karta hai"""
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, proxies=PROXIES, timeout=15)
        data = response.json()
        
        valid_pairs = []
        for item in data:
            symbol = item['symbol']
            if symbol.endswith('USDT'):
                base_asset = symbol.replace('USDT', '')
                if base_asset not in EXCLUDED_PAIRS:
                    valid_pairs.append({
                        'symbol': symbol,
                        'volume': float(item['quoteVolume'])
                    })
        
        # Sort by 24h Volume (Highest to Lowest)
        valid_pairs.sort(key=lambda x: x['volume'], reverse=True)
        return [p['symbol'] for p in valid_pairs]
    except Exception as e:
        print(f"[!] Error fetching market pairs: {e}")
        return []

def get_rotated_batch(all_pairs):
    """Coins ko rotate karke 50-50 ke batches me divider karta hai"""
    global SCAN_OFFSET
    total_pairs = len(all_pairs)
    if total_pairs == 0:
        return []
    
    # Cap total scanned pairs to Top 250-300 for high liquidity
    max_scan_limit = min(total_pairs, 250)
    
    if SCAN_OFFSET >= max_scan_limit:
        SCAN_OFFSET = 0
        
    end_offset = min(SCAN_OFFSET + BATCH_SIZE, max_scan_limit)
    batch = all_pairs[SCAN_OFFSET:end_offset]
    
    print(f"\n[🔄 Rotation Engine] Scanning coins {SCAN_OFFSET + 1} to {end_offset} of {max_scan_limit}")
    SCAN_OFFSET = end_offset
    return batch

def fetch_klines(symbol, timeframe, limit=100):
    """Binance se Candlestick Data Fetch Karta Hai"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
        
        df = pd.DataFrame(data, columns=['time', 'open', 'high', 'low', 'close', 'volume', '_', '_', '_', '_', '_', '_'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception:
        return None

# ==========================================
# TECHNICAL INDICATORS & CONFLUENCE SCORING
# ==========================================
def calculate_indicators(df):
    """Technical Indicators Calculate Karta Hai"""
    close = df['close']
    
    # 1. RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    # 2. EMA (20) & SMA (50)
    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    
    # 3. MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    
    # 4. Bollinger Bands
    sma20 = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper_band = sma20 + (std * 2)
    lower_band = sma20 - (std * 2)
    
    return {
        'price': close.iloc[-1],
        'rsi': rsi.iloc[-1],
        'ema20': ema20.iloc[-1],
        'sma50': sma50.iloc[-1],
        'macd': macd_line.iloc[-1],
        'macd_signal': signal_line.iloc[-1],
        'bb_upper': upper_band.iloc[-1],
        'bb_lower': lower_band.iloc[-1]
    }

def analyze_timeframe(df):
    """Single Timeframe ke Indicators Check Karke Score Aur Trend Nikaalta Hai"""
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"
        
    ind = calculate_indicators(df)
    price = ind['price']
    
    bull_score = 0
    bear_score = 0
    
    # RSI Condition
    if ind['rsi'] < 35:
        bull_score += 25
    elif ind['rsi'] > 65:
        bear_score += 25
        
    # EMA/SMA Trend Condition
    if price > ind['ema20'] > ind['sma50']:
        bull_score += 25
    elif price < ind['ema20'] < ind['sma50']:
        bear_score += 25
        
    # MACD Condition
    if ind['macd'] > ind['macd_signal']:
        bull_score += 25
    elif ind['macd'] < ind['macd_signal']:
        bear_score += 25
        
    # Bollinger Bands Reversal Condition
    if price <= ind['bb_lower']:
        bull_score += 25
    elif price >= ind['bb_upper']:
        bear_score += 25

    if bull_score > bear_score:
        return bull_score, "LONG"
    elif bear_score > bull_score:
        return bear_score, "SHORT"
    else:
        return 0, "NEUTRAL"

# ==========================================
# MULTI-TIMEFRAME ANALYSIS ENGINE
# ==========================================
def analyze_and_filter(symbol):
    """15m + 1h Multi-Timeframe Confirmation Logic"""
    df_15m = fetch_klines(symbol, '15m')
    df_1h = fetch_klines(symbol, '1h')
    
    score_15m, trend_15m = analyze_timeframe(df_15m)
    score_1h, trend_1h = analyze_timeframe(df_1h)
    
    # 1. Check Multi-Timeframe Trend Match
    if trend_15m == "NEUTRAL" or trend_15m != trend_1h:
        return None # Reject if trends conflict
        
    # 2. Weighted Combined Score (60% 15m + 40% 1h)
    combined_score = int((score_15m * 0.6) + (score_1h * 0.4))
    
    # 3. Strict Confluence Threshold Filter (80%+)
    if combined_score < MIN_AI_SCORE:
        return None # Reject weak setups
        
    price = df_15m['close'].iloc[-1]
    
    # Price Target & Stop Loss Calculation
    if trend_15m == "LONG":
        tp1 = round(price * 1.015, 4)
        tp2 = round(price * 1.030, 4)
        tp3 = round(price * 1.050, 4)
        sl  = round(price * 0.985, 4)
    else:
        tp1 = round(price * 0.985, 4)
        tp2 = round(price * 0.970, 4)
        tp3 = round(price * 0.950, 4)
        sl  = round(price * 1.015, 4)
        
    # Generate Formatted Telegram Signal Message
    clean_name = symbol.replace('USDT', '')
    msg = (
        f"🔥 **AI HIGH CONFLUENCE SIGNAL** 🔥\n\n"
        f"📌 **Asset:** #{clean_name} / USDT\n"
        f"🎯 **Direction:** {trend_15m}\n"
        f"📊 **AI Win Probability:** {combined_score}%\n\n"
        f"💵 **Entry Price:** `{price}`\n"
        f"🎯 **Target 1:** `{tp1}`\n"
        f"🎯 **Target 2:** `{tp2}`\n"
        f"🎯 **Target 3:** `{tp3}`\n"
        f"🛑 **Stop Loss:** `{sl}`\n\n"
        f"⚡ **Multi-TF Alignment:** 15m & 1h Confirmed\n"
        f"🛡️ **Risk Level:** Medium-Low"
    )
    
    return msg, clean_name

def send_telegram_alert(message):
    """Tor Proxy ke zariye Telegram Alert Push Karta Hai"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] Telegram Dispatch Failed: {e}")
        return False

# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
def main():
    print("🚀 Auto Signal Bot Started Successfully...")
    
    while True:
        all_pairs = get_all_usdt_pairs()
        if not all_pairs:
            print("[!] Unable to fetch market pairs. Retrying in 1 minute...")
            time.sleep(60)
            continue
            
        current_batch = get_rotated_batch(all_pairs)
        sent_count = 0
        
        for coin in current_batch:
            try:
                res = analyze_and_filter(coin)
                if res:
                    msg, coin_name = res
                    current_time = time.time()
                    
                    # Cooldown Check (10800 seconds = 3 Hours)
                    if coin_name not in sent_history or (current_time - sent_history[coin_name]) > COOLDOWN_SECONDS:
                        sent = send_telegram_alert(msg)
                        if sent:
                            sent_count += 1
                            sent_history[coin_name] = current_time
                            print(f"✅ [Signal Sent] #{coin_name}")
                        else:
                            print(f"❌ [Failed] Telegram delivery failed for #{coin_name}")
                    else:
                        print(f"⏳ #{coin_name} on cooldown. Skipped.")
                else:
                    print(f"⏩ #{coin} skipped (Score < 80% or Trend Mismatch)")
            except Exception as e:
                print(f"[!] Error analyzing #{coin}: {e}")
            
            time.sleep(1) # API Rate Limit Protection
            
        print(f"\n✅ Cycle Complete! Sent {sent_count} new high-accuracy signal(s). Sleeping 20 mins...\n")
        time.sleep(1200) # 20 Minute Sleep Cycle

if __name__ == "__main__":
    main()
