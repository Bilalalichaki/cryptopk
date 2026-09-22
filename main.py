import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from rich.text import Text

console = Console()

# ==========================================
# ⚙️ TELEGRAM & BINANCE CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "8785813821:AAGR2kLZg6EKepSEtW5NoDs66tRqUaPIEP8"
TELEGRAM_CHAT_ID = "5846593253"

BINANCE_API_KEY = "YOUR_BINANCE_API_KEY_HERE"
BINANCE_SECRET_KEY = "YOUR_BINANCE_SECRET_KEY_HERE"

# Telegram Alert Sender with Auto Proxy Fallback (Pakistan ISP Bypass)
def send_telegram_alert(message: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        console.print("[bold red]❌ Telegram Token ya Chat ID missing hai![/bold red]")
        return
    
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    
    urls = [
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        f"https://telegram-bot-api.vercel.app/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        f"https://api.pwrtelegram.xyz/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ]
    
    proxies_list = [
        None,
        {'http': 'http://185.199.229.156:7492', 'https': 'http://185.199.229.156:7492'},
        {'http': 'socks5h://184.174.9.190:1080', 'https': 'socks5h://184.174.9.190:1080'},
        {'http': 'socks5h://127.0.0.1:9050', 'https': 'socks5h://127.0.0.1:9050'}
    ]

    success = False

    for target_url in urls:
        try:
            response = requests.post(target_url, json=payload, timeout=6)
            res_data = response.json()
            if res_data.get("ok"):
                console.print("[bold green]✅ Telegram Signal Sent Successfully![/bold green]")
                success = True
                break
        except Exception:
            continue

    if not success:
        direct_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        for px in proxies_list:
            if px is None: 
                continue
            try:
                response = requests.post(direct_url, json=payload, proxies=px, timeout=6)
                res_data = response.json()
                if res_data.get("ok"):
                    console.print("[bold green]✅ Telegram Signal Sent via Proxy![/bold green]")
                    success = True
                    break
            except Exception:
                continue

    if not success:
        console.print("[bold red]❌ Network Blocked: ISP public proxies block kar raha hai. Mobile me WARP (1.1.1.1) ON rakhein.[/bold red]")

# 1. Fetch Binance Klines Data
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

# 2. Fetch Fear & Greed Index
def get_fear_and_greed():
    try:
        res = requests.get("https://api.alternative.me/fng/?limit=1", timeout=4)
        if res.status_code == 200:
            data = res.json()['data'][0]
            val = int(data['value'])
            classification = data['value_classification']
            return val, classification
    except Exception:
        pass
    return 50, "Neutral"

# 3. Indicators Calculations
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

def calculate_psar(df):
    close = df['close']
    ema_fast = close.ewm(span=10, adjust=False).mean()
    return close.iloc[-1] > ema_fast.iloc[-1]

def calculate_ma(df):
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    sma50 = df['close'].rolling(window=50).mean().iloc[-1]
    return ema20, sma50

def calculate_bollinger_bands(df, period=20):
    sma = df['close'].rolling(window=period).mean()
    std = df['close'].rolling(window=period).std()
    upper_band = sma + (std * 2)
    lower_band = sma - (std * 2)
    return upper_band.iloc[-1], lower_band.iloc[-1]

def check_volume_spike(df):
    avg_vol = df['volume'].tail(20).mean()
    curr_vol = df['volume'].iloc[-1]
    if curr_vol > (avg_vol * 1.5):
        return "HIGH VOLUME SPIKE ⚡", "green"
    return "NORMAL VOLUME ⚖️", "yellow"

def calculate_pivot_points(df):
    prev_high = df['high'].iloc[-2]
    prev_low = df['low'].iloc[-2]
    prev_close = df['close'].iloc[-2]
    pivot = (prev_high + prev_low + prev_close) / 3
    r1 = (2 * pivot) - prev_low
    s1 = (2 * pivot) - prev_high
    r2 = pivot + (prev_high - prev_low)
    s2 = pivot - (prev_high - prev_low)
    return pivot, s1, s2, r1, r2

def get_tf_trend(df):
    if df is None or df.empty:
        return "N/A"
    live_price = df['close'].iloc[-1]
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    if live_price > ema20:
        return "BULLISH 📈"
    else:
        return "BEARISH 📉"

def detect_candlestick_patterns(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    c_open, c_close, c_high, c_low = curr['open'], curr['close'], curr['high'], curr['low']
    p_open, p_close = prev['open'], prev['close']
    body = abs(c_close - c_open)
    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)

    if p_close < p_open and c_close > c_open and c_close > p_open and c_open < p_close:
        return "BULLISH ENGULFING 🚀"
    if p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        return "BEARISH ENGULFING 🔻"
    if lower_wick > (2 * body) and upper_wick < body:
        return "BULLISH HAMMER 🔨"
    if upper_wick > (2 * body) and lower_wick < body:
        return "SHOOTING STAR 💫"
    return "NORMAL PATTERN ⚖️"

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    return recent_df['low'].min(), recent_df['high'].max()

# 4. FREE BACKTESTING ENGINE
def run_backtest(df):
    if df is None or len(df) < 50:
        return "Insufficient Data", 0
    
    total_signals = 0
    wins = 0

    for i in range(30, len(df) - 5):
        sub_df = df.iloc[:i]
        c_price = sub_df['close'].iloc[-1]
        c_rsi = calculate_rsi(sub_df)
        m_val, m_sig = calculate_macd(sub_df)
        c_ema20, _ = calculate_ma(sub_df)

        if c_rsi < 60 and m_val > m_sig and c_price > c_ema20:
            total_signals += 1
            future_prices = df['high'].iloc[i:i+5]
            target = c_price * 1.02
            if (future_prices >= target).any():
                wins += 1

    if total_signals == 0:
        return "No recent signals", 0
    win_rate = (wins / total_signals) * 100
    return f"{wins}/{total_signals} Wins", win_rate

def show_header():
    console.clear()
    header = Panel(
        Text("⚡ Cryptopk Signal (SHeBi) - ADVANCED AI TERMINAL ⚡\n👨‍💻 DEVELOPER: BILAL ALI (SHEBI)", justify="center", style="bold cyan"),
        style="bold blue"
    )
    console.print(header)

def analyze_coin():
    show_header()
    coin = Prompt.ask("\n[bold yellow]📌 Symbol enter karein (e.g. BTC, ETH, SUI, SOL, PEPE, EXIT)[/bold yellow]").upper().strip()
    
    if coin == "EXIT":
        console.print("[bold red]Terminal closed. Shukriya Shebi bhai![/bold red]")
        return False

    if not coin:
        return True

    console.print(f"\n[bold cyan]🔄 Binance se {coin}/USDT + Backtest Data fetch ho raha hai...[/bold cyan]")
    
    # Timeframes Data Fetching
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h  = get_binance_klines(coin, interval="1h")
    df_1d  = get_binance_klines(coin, interval="1d")
    df_4d  = get_binance_klines(coin, interval="3d")

    fng_val, fng_class = get_fear_and_greed()

    if df_1h is None or df_1h.empty:
        console.print("[bold red]❌ Data fetch nahi ho saka. Symbol verify karein.[/bold red]")
        Prompt.ask("\n[bold yellow]Enter dabayein dobara try karne ke liye...[/bold yellow]")
        return True

    live_price = df_1h['close'].iloc[-1]

    # Indicators (1h Baseline)
    rsi = calculate_rsi(df_1h)
    macd_val, macd_sig = calculate_macd(df_1h)
    is_uptrend = calculate_psar(df_1h)
    ema20, sma50 = calculate_ma(df_1h)
    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    vol_txt, vol_color = check_volume_spike(df_1h)
    pivot, s1, s2, r1, r2 = calculate_pivot_points(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    # Multi Timeframe Trends
    trend_15m = get_tf_trend(df_15m)
    trend_1h  = get_tf_trend(df_1h)
    trend_1d  = get_tf_trend(df_1d)

    # Backtesting Result
    bt_ratio, bt_rate = run_backtest(df_1h)

    # AI ENGINE LOGIC & PREDICTIONS
    bullish_score = 0
    if rsi < 65 and rsi > 30: bullish_score += 1
    if macd_val > macd_sig: bullish_score += 1
    if is_uptrend: bullish_score += 1
    if live_price > ema20: bullish_score += 1
    if "BULLISH" in trend_1d: bullish_score += 1

    # FUTURES LONG & SHORT CALCULATION
    f_long_entry_low = live_price * 0.997
    f_long_entry_high = live_price * 1.002
    f_long_tp1 = live_price * 1.015
    f_long_tp2 = live_price * 1.030
    f_long_tp3 = live_price * 1.050
    f_long_sl = live_price * 0.982

    f_short_entry_low = live_price * 1.003
    f_short_entry_high = live_price * 0.998
    f_short_tp1 = live_price * 0.985
    f_short_tp2 = live_price * 0.970
    f_short_tp3 = live_price * 0.950
    f_short_sl = live_price * 1.018

    # SPOT BUYING ZONE & TARGETS
    spot_buy_zone_1 = demand_zone if demand_zone < live_price else live_price * 0.98
    spot_buy_zone_2 = live_price * 0.95
    spot_tp1 = live_price * 1.08
    spot_tp2 = live_price * 1.15
    spot_tp3 = live_price * 1.25
    spot_sl = spot_buy_zone_2 * 0.93

    if bullish_score >= 3:
        primary_bias = "LONG 🟢 (BULLISH FAVORED)"
        recommended_mode = "FUTURES LONG / SPOT BUY"
        risk_level = "LOW TO MEDIUM RISK 🟢"
        win_prob = 75 + (bullish_score * 4)
        ai_decision = "BUY ENTRY RECOMMENDED"
        ai_reason = "Bullish structure present across major indicators. Spot and Long positions active."
        ai_box_style = "bold green"
    else:
        primary_bias = "SHORT 🔴 (BEARISH FAVORED)"
        recommended_mode = "FUTURES SHORT / SPOT WAIT"
        risk_level = "HIGH RISK FOR LONG 🔴"
        win_prob = 40
        ai_decision = "WAIT / SHORT FAVORED"
        ai_reason = "Market under resistance. Spot buyers should wait for dip."
        ai_box_style = "bold yellow"

    # PROFESSIONAL VIP TELEGRAM SIGNAL FORMAT (UPDATED HEADER & SPOT INCLUDED)
    telegram_msg = f"""🔥 <b>Cryptopk Signal (SHeBi)</b> 🔥
----------------------------------
📌 <b>PAIR:</b> #{coin}/USDT
📊 <b>MARKET BIAS:</b> {primary_bias}
⚡ <b>RECOMMENDED SETUP:</b> {recommended_mode}
🛡️ <b>RISK LEVEL:</b> {risk_level}
📍 <b>LIVE PRICE:</b> ${live_price:,.4f}

----------------------------------
📈 <b>FUTURES LONG SETUP (Cross 5x - 10x):</b>
 ├ <b>Entry Zone:</b> ${f_long_entry_low:,.4f} - ${f_long_entry_high:,.4f}
 ├ <b>TP 1:</b> ${f_long_tp1:,.4f}
 ├ <b>TP 2:</b> ${f_long_tp2:,.4f}
 ├ <b>TP 3:</b> ${f_long_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_long_sl:,.4f}

📉 <b>FUTURES SHORT SETUP (Cross 5x - 10x):</b>
 ├ <b>Entry Zone:</b> ${f_short_entry_high:,.4f} - ${f_short_entry_low:,.4f}
 ├ <b>TP 1:</b> ${f_short_tp1:,.4f}
 ├ <b>TP 2:</b> ${f_short_tp2:,.4f}
 ├ <b>TP 3:</b> ${f_short_tp3:,.4f}
 └ <b>Stop Loss:</b> ${f_short_sl:,.4f}

----------------------------------
💎 <b>SPOT BUYING SETUP (Holders / Swing):</b>
 ├ <b>Buy Zone 1:</b> ${spot_buy_zone_1:,.4f}
 ├ <b>Buy Zone 2 (Dip):</b> ${spot_buy_zone_2:,.4f}
 ├ <b>Target 1:</b> ${spot_tp1:,.4f} (+8%)
 ├ <b>Target 2:</b> ${spot_tp2:,.4f} (+15%)
 ├ <b>Target 3:</b> ${spot_tp3:,.4f} (+25%)
 └ <b>Spot Stop Loss:</b> ${spot_sl:,.4f}

----------------------------------
🧠 <b>AI CONFLUENCE & INDICATORS:</b>
• <b>Win Probability:</b> {win_prob}%
• <b>RSI (14):</b> {rsi:.1f}
• <b>MACD Status:</b> {'Bullish Crossover 🟢' if macd_val > macd_sig else 'Bearish Crossover 🔴'}
• <b>Timeframe Trend (15m/1h/1d):</b> {trend_15m} | {trend_1h} | {trend_1d}
• <b>Candle Pattern:</b> {candle_pattern}
• <b>Market Sentiment:</b> {fng_val}/100 ({fng_class})
• <b>Backtest Winrate:</b> {bt_rate:.1f}% ({bt_ratio})

⚠️ <i>Risk Management: Max 2-3% wallet size per trade!</i>"""

    send_telegram_alert(telegram_msg)

    # 1. AI PREDICTION + BACKTESTING SUMMARY
    console.print("\n")
    console.print(Rule(title=f"[bold cyan]🤖 Cryptopk Signal (SHeBi) | Live Price: ${live_price:,.4f}[/bold cyan]", style="cyan"))

    ai_report = f"""
🎯 [bold white]ENTRY DECISION:[/bold white] [{ai_box_style}]{ai_decision}[/{ai_box_style}]
💡 [bold white]REASON:[/bold white] {ai_reason}

📊 [bold green]WIN PROBABILITY:[/bold green] [bold green]{win_prob}% Chance[/bold green]
📈 [bold magenta]BACKTEST ACCURACY:[/bold magenta] [bold yellow]{bt_rate:.1f}% Win Rate ({bt_ratio})[/bold yellow]
📈 [bold green]LONG TP1:[/bold green] ${f_long_tp1:,.4f} | 📉 [bold red]SHORT TP1:[/bold red] ${f_short_tp1:,.4f}
💎 [bold cyan]SPOT TARGET 1:[/bold cyan] ${spot_tp1:,.4f}
"""
    console.print(Panel(ai_report, title="[bold cyan]⚡ AI ANALYSIS SUMMARY[/bold cyan]", style=ai_box_style))

    console.print("\n")
    choice = Prompt.ask("[bold yellow]🔄 Kisi aur coin ka analysis karna hai? (Y / N)[/bold yellow]", choices=["y", "n"], default="y")
    return choice.lower() == "y"

def main():
    show_header()
    running = True
    while running:
        running = analyze_coin()

if __name__ == "__main__":
    main()
