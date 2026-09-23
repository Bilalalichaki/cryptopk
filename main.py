import requests
import pandas as pd
import numpy as np
import time
import html
from rich.console import Console
from rich.panel import Panel

console = Console()

# ==========================================
# ⚙️ TELEGRAM CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8785813821:AAGR2kLZg6EKepSEtW5NoDs66tRqUaPIEP8"
TELEGRAM_CHAT_ID = "-1004458934308" 

def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    # Local Tor SOCKS5 Proxy to bypass ISP blocks in Pakistan
   # proxies = {
   #     'http': 'socks5h://127.0.0.1:9050',
  #      'https': 'socks5h://127.0.0.1:9050'
   # }

    try:
        res = requests.post(url, json=payload, proxies=proxies, timeout=15)
        if res.status_code == 200 and res.json().get("ok"):
            return True
        else:
            if res.text:
                console.print(f"[bold red]❌ Telegram Error: {res.text}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]❌ Request Error: {e}[/bold red]")

    return False

def get_top_coins(limit=100):
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT') and not item['symbol'].startswith('UP') and not item['symbol'].startswith('DOWN')]
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        top_coins = [item['symbol'].replace('USDT', '') for item in sorted_pairs[:limit]]
        return top_coins
    except Exception as e:
        console.print(f"[bold red]❌ Binance Top Coins fetch error: {e}[/bold red]")
        return []

def get_binance_klines(symbol: str, interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if isinstance(data, dict) and "code" in data:
            return None
        df = pd.DataFrame(data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
        ])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception:
        return None

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_macd(df, fast=12, slow=26, signal=9):
    exp1 = df['close'].ewm(span=fast, adjust=False).mean()
    exp2 = df['close'].ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    macd_signal = macd.ewm(span=signal, adjust=False).mean()
    return macd.iloc[-1], macd_signal.iloc[-1]

def calculate_ma(df):
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    sma50 = df['close'].rolling(window=50).mean().iloc[-1]
    return ema20, sma50

def calculate_bollinger_bands(df, period=20):
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper = sma + (std * 2)
    lower = sma - (std * 2)
    return upper.iloc[-1], lower.iloc[-1]

def check_volume_spike(df):
    avg_vol = df['volume'].tail(20).mean()
    curr_vol = df['volume'].iloc[-1]
    if curr_vol > (avg_vol * 1.5):
        return "HIGH VOLUME SPIKE ⚡"
    return "NORMAL VOLUME ⚖️"

def calculate_stoch_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    stoch_rsi = (rsi - rsi.rolling(period).min()) / (rsi.rolling(period).max() - rsi.rolling(period).min())
    k = stoch_rsi.rolling(3).mean() * 100
    return k.iloc[-1]

def calculate_vwap(df):
    tp = (df['high'] + df['low'] + df['close']) / 3
    vwap = (tp * df['volume']).cumsum() / df['volume'].cumsum()
    return vwap.iloc[-1]

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(period).mean()
    return atr.iloc[-1]

def get_tf_trend(df):
    if df is None or df.empty:
        return "N/A"
    live_price = df['close'].iloc[-1]
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    return "BULLISH 📈" if live_price > ema20 else "BEARISH 📉"

def analyze_candlestick_details(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    c_open, c_close, c_high, c_low = curr['open'], curr['close'], curr['high'], curr['low']
    p_open, p_close = prev['open'], prev['close']
    
    body = abs(c_close - c_open)
    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)
    total_range = c_high - c_low

    pattern_name = "Normal Candle"
    candle_strength = "Moderate / Neutral"
    weakness_zone = "No Major Weakness"

    if p_close < p_open and c_close > c_open and c_close > p_open and c_open < p_close:
        pattern_name = "Bullish Engulfing 🚀"
        candle_strength = "STRONG BUYING PRESSURE 💪"
        weakness_zone = f"Weakness below ${c_low:,.4f}"
    elif p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        pattern_name = "Bearish Engulfing 🔻"
        candle_strength = "STRONG SELLING PRESSURE ⚠️"
        weakness_zone = f"Weakness below ${c_close:,.4f}"
    elif lower_wick > (2 * body) and upper_wick < body:
        pattern_name = "Bullish Hammer 🔨"
        candle_strength = "REJECTION FROM LOWS (Strong Dip Buy)"
        weakness_zone = f"Break below ${c_low:,.4f} invalidates setup"
    elif upper_wick > (2 * body) and lower_wick < body:
        pattern_name = "Shooting Star / Upper Wick Rejection 💫"
        candle_strength = "WEAKNESS AT HIGHS (Sellers Active)"
        weakness_zone = f"Heavy resistance near ${c_high:,.4f}"
    else:
        if c_close > c_open and body > (total_range * 0.6):
            pattern_name = "Strong Bullish Marubozu 🟩"
            candle_strength = "HIGH MOMENTUM BULLS"
            weakness_zone = f"Weakness if price drops below ${c_open:,.4f}"
        elif c_close < c_open and body > (total_range * 0.6):
            pattern_name = "Strong Bearish Marubozu 🟥"
            candle_strength = "HIGH MOMENTUM BEARS"
            weakness_zone = f"Weakness below ${c_close:,.4f}"

    return pattern_name, candle_strength, weakness_zone

def analyze_and_filter(coin: str, force_send=False):
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h  = get_binance_klines(coin, interval="1h")
    df_1d  = get_binance_klines(coin, interval="1d")

    if df_1h is None or df_1h.empty:
        return None

    live_price = df_1h['close'].iloc[-1]

    rsi = calculate_rsi(df_1h)
    macd_val, macd_sig = calculate_macd(df_1h)
    ema20, sma50 = calculate_ma(df_1h)
    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    vol_status = check_volume_spike(df_1h)
    stoch_k = calculate_stoch_rsi(df_1h)
    vwap_val = calculate_vwap(df_1h)
    atr_val = calculate_atr(df_1h)

    candle_pattern, candle_strength, weakness_info = analyze_candlestick_details(df_1h)

    trend_15m = get_tf_trend(df_15m)
    trend_1h  = get_tf_trend(df_1h)
    trend_1d  = get_tf_trend(df_1d)

    bullish_score = 0
    bearish_score = 0

    if 35 < rsi < 65: bullish_score += 1
    if macd_val > macd_sig: bullish_score += 1
    if live_price > ema20: bullish_score += 1
    if "BULLISH" in trend_1d: bullish_score += 1
    if live_price > vwap_val: bullish_score += 1
    if 20 < stoch_k < 80: bullish_score += 1

    if rsi > 65 or rsi < 35: bearish_score += 1
    if macd_val < macd_sig: bearish_score += 1
    if live_price < ema20: bearish_score += 1
    if "BEARISH" in trend_1d: bearish_score += 1

    # Single search option me filter bypass ho jayega
    if not force_send and (bullish_score < 4 and bearish_score < 4):
        return None

    if bullish_score >= bearish_score:
        primary_bias = "LONG 🟢 (STRONG BULLISH)"
        where_to_trade = "✅ FUTURES LONG &amp; SPOT BUY BOTH (Best Opportunity)"
        recommended_mode = "FUTURES LONG / SPOT BUY"
        risk_level = "LOW RISK 🟢"
        win_prob = min(95, 82 + (bullish_score * 3))
    else:
        primary_bias = "SHORT 🔴 (STRONG BEARISH)"
        where_to_trade = "⚠️ FUTURES SHORT ONLY (Avoid Spot Buy)"
        recommended_mode = "FUTURES SHORT ONLY"
        risk_level = "MEDIUM TO HIGH RISK 🔴"
        win_prob = 75

    f_long_entry_low, f_long_entry_high = live_price * 0.997, live_price * 1.002
    f_long_tp1, f_long_tp2, f_long_tp3 = live_price * 1.015, live_price * 1.030, live_price * 1.050
    f_long_sl = live_price * 0.982

    f_short_entry_low, f_short_entry_high = live_price * 0.998, live_price * 1.003
    f_short_tp1, f_short_tp2, f_short_tp3 = live_price * 0.985, live_price * 0.970, live_price * 0.950
    f_short_sl = live_price * 1.018

    spot_buy_1 = live_price * 0.98
    spot_buy_2 = live_price * 0.95
    spot_tp1 = live_price * 1.08
    spot_tp2 = live_price * 1.15
    spot_tp3 = live_price * 1.25
    spot_sl = spot_buy_2 * 0.93

    telegram_msg = f"""🔥 <b>BEST TRADE OPPORTUNITY (Cryptopk - SHeBi)</b> 🔥
----------------------------------
📌 <b>PAIR:</b> #{coin.upper()}/USDT
📊 <b>MARKET BIAS:</b> {primary_bias}
🎯 <b>TRADE RECOMMENDATION:</b>
<b>{where_to_trade}</b>
⚡ <b>SETUP:</b> {recommended_mode}
🛡️ <b>RISK LEVEL:</b> {risk_level}
📍 <b>CURRENT PRICE:</b> ${live_price:,.4f}

----------------------------------
🕯️ <b>CANDLESTICK &amp; STRUCTURE ANALYSIS:</b>
• <b>Active Pattern:</b> {candle_pattern}
• <b>Candle Strength:</b> {candle_strength}
• <b>Weakness / Danger Zone:</b> {weakness_info}

----------------------------------
📈 <b>FUTURES LONG (Cross 5x-10x):</b>
 ├ <b>Entry Zone:</b> ${f_long_entry_low:,.4f} - ${f_long_entry_high:,.4f}
 ├ <b>TP 1:</b> ${f_long_tp1:,.4f} | <b>TP 2:</b> ${f_long_tp2:,.4f} | <b>TP 3:</b> ${f_long_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_long_sl:,.4f}

📉 <b>FUTURES SHORT (Cross 5x-10x):</b>
 ├ <b>Entry Zone:</b> ${f_short_entry_high:,.4f} - ${f_short_entry_low:,.4f}
 ├ <b>TP 1:</b> ${f_short_tp1:,.4f} | <b>TP 2:</b> ${f_short_tp2:,.4f} | <b>TP 3:</b> ${f_short_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_short_sl:,.4f}

----------------------------------
💎 <b>SPOT BUYING SETUP:</b>
 ├ <b>Buy Zones:</b> ${spot_buy_1:,.4f} | ${spot_buy_2:,.4f}
 ├ <b>Targets:</b> ${spot_tp1:,.4f} (+8%) | ${spot_tp2:,.4f} (+15%) | ${spot_tp3:,.4f} (+25%)
 └ <b>Stop Loss:</b> ${spot_sl:,.4f}

----------------------------------
🧠 <b>ALL INDICATORS &amp; CONFLUENCE:</b>
• <b>AI Win Probability:</b> {win_prob}%
• <b>RSI (14):</b> {rsi:.2f} ({'Oversold 🟢' if rsi < 30 else 'Overbought 🔴' if rsi > 70 else 'Neutral ⚖️'})
• <b>Stoch RSI (K):</b> {stoch_k:.1f}
• <b>VWAP:</b> ${vwap_val:,.4f} | <b>ATR (Volatilty):</b> ${atr_val:,.4f}
• <b>MACD Status:</b> {'Bullish Crossover 🟢' if macd_val > macd_sig else 'Bearish Crossover 🔴'}
• <b>EMA 20 / SMA 50:</b> ${ema20:,.4f} / ${sma50:,.4f}
• <b>Bollinger Upper/Lower:</b> ${upper_bb:,.4f} / ${lower_bb:,.4f}
• <b>Volume Status:</b> {vol_status}
• <b>Trend (15m / 1h / 1d):</b> {trend_15m} | {trend_1h} | {trend_1d}
"""
    return telegram_msg, coin.upper()

def main():
    console.clear()
    console.print(Panel("[bold cyan]🚀 CRYPTOPK AI SIGNAL GENERATOR (SHeBi) 🚀[/bold cyan]", style="bold blue"))
    
    console.print("[bold yellow]Select Scan Option:[/bold yellow]")
    console.print("1. Scan Top 10 Coins")
    console.print("2. Scan Top 20 Coins")
    console.print("3. Scan Top 100 Coins")
    console.print("4. Search & Analyze Single Custom Coin (e.g., BTC, ETH, SOL)")
    
    choice = input("\nEnter choice (1, 2, 3, or 4): ").strip()
    
    coins_to_scan = []
    force_send = False

    if choice == "1":
        coins_to_scan = get_top_coins(10)
    elif choice == "2":
        coins_to_scan = get_top_coins(20)
    elif choice == "3":
        coins_to_scan = get_top_coins(100)
    elif choice == "4":
        custom_coin = input("Enter Coin Symbol (e.g., SOL or BTC): ").strip().upper()
        custom_coin = custom_coin.replace("USDT", "")
        coins_to_scan = [custom_coin]
        force_send = True  # Single search me AI setup direct alert bhejega
    else:
        console.print("[bold red]Invalid option! Defaulting to Top 100 Coins.[/bold red]")
        coins_to_scan = get_top_coins(100)

    if not coins_to_scan:
        console.print("[bold red]❌ Coins list fetch nahi ho saki.[/bold red]")
        return

    console.print(f"\n[bold yellow]📊 Filtering {len(coins_to_scan)} Coin(s) on Binance...[/bold yellow]\n")

    best_trades_count = 0
    for idx, coin in enumerate(coins_to_scan, 1):
        try:
            res = analyze_and_filter(coin, force_send=force_send)
            if res:
                msg, coin_name = res
                sent = send_telegram_alert(msg)
                if sent:
                    best_trades_count += 1
                    console.print(f"[bold green]🔥 [BEST TRADE #{best_trades_count}] Signal Sent for #{coin_name}[/bold green]")
                else:
                    console.print(f"[bold red]❌ Failed to send Telegram alert for #{coin_name}[/bold red]")
            else:
                console.print(f"[dim gray]⏭️ [{idx}/{len(coins_to_scan)}] #{coin} skipped (Weak Setup)[/dim gray]")
            time.sleep(1.2)
        except Exception as e:
            console.print(f"[bold red]❌ Error scanning {coin}: {e}[/bold red]")
            continue

    console.print(f"\n[bold green]🎉 COMPLETE! Total {best_trades_count} Best Trade Signal(s) sent to Telegram.[/bold green]")

if __name__ == "__main__":
    main()
