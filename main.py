import requests
import pandas as pd
import time
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()

# ==========================================
# ⚙️ TELEGRAM CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8785813821:AAGR2kLZg6EKepSEtW5NoDs66tRqUaPIEP8"
TELEGRAM_CHAT_ID = "5846593253"

# Telegram Alert Sender with Auto Proxy Fallback
def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    urls = [
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        f"https://telegram-bot-api.vercel.app/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        f"https://api.api.pwrtelegram.xyz/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ]
    
    proxies_list = [
        None,
        {'http': 'http://185.199.229.156:7492', 'https': 'http://185.199.229.156:7492'},
        {'http': 'socks5h://184.174.9.190:1080', 'https': 'socks5h://184.174.9.190:1080'},
        {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}
    ]

    for target_url in urls:
        try:
            res = requests.post(target_url, json=payload, timeout=6)
            if res.json().get("ok"):
                return
        except Exception:
            continue

    direct_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for px in proxies_list:
        if px is None: 
            continue
        try:
            res = requests.post(direct_url, json=payload, proxies=px, timeout=6)
            if res.json().get("ok"):
                return
        except Exception:
            continue

# 1. Fetch Top 100 USDT Pairs by Volume from Binance
def get_top_100_coins():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT') and not item['symbol'].startswith('UP') and not item['symbol'].startswith('DOWN')]
        # Sort by 24h Volume
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        top_100 = [item['symbol'].replace('USDT', '') for item in sorted_pairs[:100]]
        return top_100
    except Exception as e:
        console.print(f"[bold red]❌ Binance Top 100 fetch error: {e}[/bold red]")
        return []

# 2. Fetch Binance Klines Data
def get_binance_klines(symbol: str, interval="1h", limit=100):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval={interval}&limit={limit}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
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

# Indicators Calculations
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
    return ema20

def get_tf_trend(df):
    if df is None or df.empty:
        return "N/A"
    live_price = df['close'].iloc[-1]
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    return "BULLISH 📈" if live_price > ema20 else "BEARISH 📉"

def analyze_and_send(coin: str, count: int):
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h  = get_binance_klines(coin, interval="1h")
    df_1d  = get_binance_klines(coin, interval="1d")

    if df_1h is None or df_1h.empty:
        return

    live_price = df_1h['close'].iloc[-1]

    # Indicators
    rsi = calculate_rsi(df_1h)
    macd_val, macd_sig = calculate_macd(df_1h)
    ema20 = calculate_ma(df_1h)

    # Multi Timeframe Trends
    trend_15m = get_tf_trend(df_15m)
    trend_1h  = get_tf_trend(df_1h)
    trend_1d  = get_tf_trend(df_1d)

    # Bullish Logic
    bullish_score = 0
    if 30 < rsi < 65: bullish_score += 1
    if macd_val > macd_sig: bullish_score += 1
    if live_price > ema20: bullish_score += 1
    if "BULLISH" in trend_1d: bullish_score += 1

    # Futures Setups
    f_long_entry_low, f_long_entry_high = live_price * 0.997, live_price * 1.002
    f_long_tp1, f_long_tp2, f_long_tp3 = live_price * 1.015, live_price * 1.030, live_price * 1.050
    f_long_sl = live_price * 0.982

    f_short_entry_low, f_short_entry_high = live_price * 0.998, live_price * 1.003
    f_short_tp1, f_short_tp2, f_short_tp3 = live_price * 0.985, live_price * 0.970, live_price * 0.950
    f_short_sl = live_price * 1.018

    # Spot Setups
    spot_buy_1 = live_price * 0.98
    spot_buy_2 = live_price * 0.95
    spot_tp1 = live_price * 1.08
    spot_tp2 = live_price * 1.15
    spot_tp3 = live_price * 1.25
    spot_sl = spot_buy_2 * 0.93

    if bullish_score >= 3:
        primary_bias = "LONG 🟢 (BULLISH)"
        recommended_mode = "FUTURES LONG / SPOT BUY"
        risk_level = "LOW TO MEDIUM RISK 🟢"
        win_prob = 75 + (bullish_score * 4)
    else:
        primary_bias = "SHORT 🔴 (BEARISH)"
        recommended_mode = "FUTURES SHORT / SPOT WAIT"
        risk_level = "HIGH RISK FOR LONG 🔴"
        win_prob = 45

    # Message Format
    telegram_msg = f"""🔥 <b>Cryptopk Signal (SHeBi) #{count}</b> 🔥
----------------------------------
📌 <b>PAIR:</b> #{coin}/USDT
📊 <b>MARKET BIAS:</b> {primary_bias}
⚡ <b>SETUP:</b> {recommended_mode}
🛡️ <b>RISK LEVEL:</b> {risk_level}
📍 <b>PRICE:</b> ${live_price:,.4f}

----------------------------------
📈 <b>FUTURES LONG (Cross 5x-10x):</b>
 ├ <b>Entry:</b> ${f_long_entry_low:,.4f} - ${f_long_entry_high:,.4f}
 ├ <b>TP 1:</b> ${f_long_tp1:,.4f} | <b>TP 2:</b> ${f_long_tp2:,.4f} | <b>TP 3:</b> ${f_long_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_long_sl:,.4f}

📉 <b>FUTURES SHORT (Cross 5x-10x):</b>
 ├ <b>Entry:</b> ${f_short_entry_high:,.4f} - ${f_short_entry_low:,.4f}
 ├ <b>TP 1:</b> ${f_short_tp1:,.4f} | <b>TP 2:</b> ${f_short_tp2:,.4f} | <b>TP 3:</b> ${f_short_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_short_sl:,.4f}

----------------------------------
💎 <b>SPOT BUYING SETUP:</b>
 ├ <b>Buy Zones:</b> ${spot_buy_1:,.4f} | ${spot_buy_2:,.4f}
 ├ <b>Targets:</b> ${spot_tp1:,.4f} (+8%) | ${spot_tp2:,.4f} (+15%) | ${spot_tp3:,.4f} (+25%)
 └ <b>Stop Loss:</b> ${spot_sl:,.4f}

----------------------------------
🧠 <b>INDICATORS:</b>
• <b>Win Prob:</b> {win_prob}% | <b>RSI:</b> {rsi:.1f}
• <b>Trend (15m/1h/1d):</b> {trend_15m} | {trend_1h} | {trend_1d}
• <b>MACD:</b> {'Bullish 🟢' if macd_val > macd_sig else 'Bearish 🔴'}
"""

    send_telegram_alert(telegram_msg)
    console.print(f"[bold green]✅ [{count}/100] Signal Sent for #{coin}[/bold green]")

def main():
    console.clear()
    console.print(Panel("[bold cyan]🚀 STARTING AUTOMATED SCANNER FOR TOP 100 COINS 🚀\nCryptopk Signal (SHeBi)[/bold cyan]", style="bold blue"))
    
    top_coins = get_top_100_coins()
    if not top_coins:
        console.print("[bold red]❌ Coins list fetch nahi ho saki.[/bold red]")
        return

    console.print(f"[bold yellow]📊 Found Top {len(top_coins)} Coins on Binance by Volume.[/bold yellow]\n")

    for idx, coin in enumerate(top_coins, 1):
        try:
            analyze_and_send(coin, idx)
            # Binance API Limit Rate Safe keeping + Telegram Spam Prevention
            time.sleep(1.5)
        except Exception as e:
            console.print(f"[bold red]❌ Error scanning {coin}: {e}[/bold red]")
            continue

    console.print("\n[bold green]🎉 SCANNING COMPLETE! Top 100 Signals sent to Telegram.[/bold green]")

if __name__ == "__main__":
    main()
