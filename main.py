import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from rich.text import Text

console = Console()

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

# 3. Indicator Calculations
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
        return "[bold green]BULLISH 📈[/bold green]"
    else:
        return "[bold red]BEARISH 📉[/bold red]"

def detect_candlestick_patterns(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    c_open, c_close, c_high, c_low = curr['open'], curr['close'], curr['high'], curr['low']
    p_open, p_close = prev['open'], prev['close']
    body = abs(c_close - c_open)
    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)

    if p_close < p_open and c_close > c_open and c_close > p_open and c_open < p_close:
        return "[bold green]BULLISH ENGULFING 🚀 (BUY PATTERN)[/bold green]"
    if p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        return "[bold red]BEARISH ENGULFING 🔻 (SELL PATTERN)[/bold red]"
    if lower_wick > (2 * body) and upper_wick < body:
        return "[bold green]BULLISH HAMMER 🔨 (BUY PATTERN)[/bold green]"
    if upper_wick > (2 * body) and lower_wick < body:
        return "[bold red]SHOOTING STAR 💫 (SELL PATTERN)[/bold red]"
    return "[bold yellow]NORMAL CANDLE ⚖️[/bold yellow]"

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    return recent_df['low'].min(), recent_df['high'].max()

def show_header():
    console.clear()
    header = Panel(
        Text("⚡ CRYPTO ADVANCED AI & TECHNICAL TERMINAL ⚡\n👨‍💻 DEVELOPER: BILAL ALI (SHEBI)", justify="center", style="bold cyan"),
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

    console.print(f"\n[bold cyan]🔄 Binance se {coin}/USDT + BTC Market Context fetch ho raha hai...[/bold cyan]")
    
    # Timeframes Data Fetching
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h  = get_binance_klines(coin, interval="1h")
    df_1d  = get_binance_klines(coin, interval="1d")
    df_4d  = get_binance_klines(coin, interval="3d")
    df_btc = get_binance_klines("BTC", interval="1h")

    # Fear & Greed Index
    fng_val, fng_class = get_fear_and_greed()

    if df_1h is None or df_1h.empty:
        console.print("[bold red]❌ Data fetch nahi ho saka. Symbol verify karein.[/bold red]")
        Prompt.ask("\n[bold yellow]Enter dabayein dobara try karne ke liye...[/bold yellow]")
        return True

    live_price = df_1h['close'].iloc[-1]

    # BTC Correlation & Alert
    btc_change = 0
    if df_btc is not None and not df_btc.empty:
        btc_open = df_btc['open'].iloc[-1]
        btc_close = df_btc['close'].iloc[-1]
        btc_change = ((btc_close - btc_open) / btc_open) * 100

    if abs(btc_change) > 1.8:
        btc_alert = f"[bold red]⚠️ HIGH BTC VOLATILITY ({btc_change:+.2f}%): Altcoin risk me hai![/bold red]"
    else:
        btc_alert = f"[bold green]✅ BTC STABLE ({btc_change:+.2f}%): Market range normal hai.[/bold green]"

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
    trend_4d  = get_tf_trend(df_4d)

    # AI ENGINE LOGIC & PREDICTIONS
    bullish_score = 0
    if rsi < 65 and rsi > 30: bullish_score += 1
    if macd_val > macd_sig: bullish_score += 1
    if is_uptrend: bullish_score += 1
    if live_price > ema20: bullish_score += 1
    if "BULLISH" in trend_1d: bullish_score += 1

    # New Advanced Metric Calculations
    trigger_rate = r1 if r1 > live_price else live_price * 1.008
    trailing_sl = live_price * 0.992

    if bullish_score >= 4:
        ai_decision = "[bold green]🚀 BUY ENTRY RECOMMENDED (ENTRY LENA CHAHIYE)[/bold green]"
        ai_target = r1 if r1 > live_price else live_price * 1.04
        ai_sl = s1 if s1 < live_price else live_price * 0.98
        win_prob = 75 + (bullish_score * 4)
        ai_box_style = "bold green"
        ai_reason = "Major timeframes me strong bullish momentum hai. Indicators safe buying zone me hain."
    elif bullish_score <= 1 or rsi > 70:
        ai_decision = "[bold red]🛑 NO ENTRY / HIGH RISK (ENTRY NA LEIN)[/bold red]"
        ai_target = live_price * 0.95
        ai_sl = supply_zone * 1.01
        win_prob = 25
        ai_box_style = "bold red"
        ai_reason = "Market overbought hai ya high resistance level par hai. Dump ka risk zyada hai."
    else:
        ai_decision = "[bold yellow]⏳ WAIT & WATCH (INTEZAR KAREIN)[/bold yellow]"
        ai_target = r1
        ai_sl = s1
        win_prob = 50
        ai_box_style = "bold yellow"
        ai_reason = "Market range-bound hai. Specific breakout level Ka wait karein."

    target_pct = ((ai_target - live_price) / live_price) * 100
    sl_pct = ((live_price - ai_sl) / live_price) * 100
    risk_reward = abs(target_pct / sl_pct) if sl_pct > 0 else 1.0

    # ---------------------------------------------------------
    # 1. AI PREDICTION ENGINE OUTPUT (WITH 5 NEW FEATURES)
    # ---------------------------------------------------------
    console.print("\n")
    console.print(Rule(title=f"[bold cyan]🤖 ADVANCED AI PREDICTION ({coin}/USDT) | Live Price: ${live_price:,.4f}[/bold cyan]", style="cyan"))

    ai_report = f"""
🎯 [bold white]ENTRY DECISION:[/bold white] {ai_decision}
💡 [bold white]REASON (Wajah):[/bold white] {ai_reason}

📊 [bold green]WIN PROBABILITY:[/bold green] [bold green]{win_prob}% Chance[/bold green] | [bold cyan]Risk-to-Reward Ratio:[/bold cyan] 1 : {risk_reward:.2f}
🚀 [bold green]EXPECTED TARGET:[/bold green] [bold green]${ai_target:,.4f}[/bold green] ([bold green]{target_pct:+.2f}%[/bold green])
🛡️ [bold red]STOP LOSS:[/bold red] [bold red]${ai_sl:,.4f}[/bold red] ([bold red]-{sl_pct:.2f}%[/bold red])

🔑 [bold yellow]BREAKOUT TRIGGER RATE:[/bold yellow] ${trigger_rate:,.4f} (Is level ke ooper buy karein)
🔄 [bold magenta]TRAILING STOP LOSS:[/bold magenta] ${trailing_sl:,.4f} (Profit safe rakhne ke liye)
"""
    console.print(Panel(ai_report, title="[bold cyan]⚡ AI ANALYSIS SUMMARY & PROBABILITY[/bold cyan]", style=ai_box_style))

    # ---------------------------------------------------------
    # 2. MARKET SENTIMENT & BTC ALERT
    # ---------------------------------------------------------
    sentiment_info = f"""
🌡️ [bold white]Fear & Greed Index:[/bold white] [bold yellow]{fng_val}/100 ({fng_class})[/bold yellow]
⚡ [bold white]Bitcoin Correlation Alert:[/bold white] {btc_alert}
"""
    console.print(Panel(sentiment_info, title="[bold cyan]🌐 MARKET SENTIMENT & BTC ALERT[/bold cyan]", style="yellow"))

    # ---------------------------------------------------------
    # 3. TIMEFRAME ANALYSIS (15m, 1h, 1d, 4d)
    # ---------------------------------------------------------
    tf_summary = f"""
[bold white]15m Timeframe:[/bold white] {trend_15m}  |  [bold white]1h Timeframe:[/bold white] {trend_1h}
[bold white]1d Timeframe:[/bold white] {trend_1d}  |  [bold white]4d Timeframe:[/bold white] {trend_4d}
"""
    console.print(Panel(tf_summary, title="[bold cyan]⏱️ MULTI-TIMEFRAME ANALYSIS (15m, 1h, 1d, 4d)[/bold cyan]", style="blue"))

    # ---------------------------------------------------------
    # 4. PURE TECHNICAL INDICATORS (SAB PURANE REHNE DIYE HAIN)
    # ---------------------------------------------------------
    console.print(Rule(title=f"[bold magenta]📊 ALL 10 TECHNICAL INDICATORS BREAKDOWN[/bold magenta]", style="magenta"))

    # RSI
    rsi_txt = f"Value: {rsi:.2f} -> " + ("OVERSOLD 📈 (BUY)" if rsi < 30 else "OVERBOUGHT 📉 (SELL)" if rsi > 70 else "NEUTRAL ⚖️")
    console.print(Panel(rsi_txt, title="1️⃣ RSI (14) Indicator", style="green" if rsi < 60 else "red"))

    # MACD
    macd_txt = f"MACD: {macd_val:.4f} | Signal: {macd_sig:.4f} -> " + ("BULLISH CROSSOVER 🟢" if macd_val > macd_sig else "BEARISH CROSSOVER 🔴")
    console.print(Panel(macd_txt, title="2️⃣ MACD Indicator", style="green" if macd_val > macd_sig else "red"))

    # PSAR & Moving Averages
    ma_txt = f"PSAR Status: {'UPTREND 📈' if is_uptrend else 'DOWNTREND 📉'}\nEMA20: ${ema20:,.4f} | SMA50: ${sma50:,.4f}"
    console.print(Panel(ma_txt, title="3️⃣ PSAR & Moving Averages (EMA20 vs SMA50)", style="cyan"))

    # Bollinger Bands & Volume
    vol_bb = f"Upper Band: ${upper_bb:,.4f} | Lower Band: ${lower_bb:,.4f}\nVolume Trend: {vol_txt}"
    console.print(Panel(vol_bb, title="4️⃣ Bollinger Bands & Volume Spike Scanner", style="blue"))

    # Demand / Supply
    ds_info = f"Demand Zone (Support Area): ${demand_zone:,.4f} | Supply Zone (Resistance Area): ${supply_zone:,.4f}"
    console.print(Panel(ds_info, title="5️⃣ Demand & Supply Zones", style="magenta"))

    # Pivots
    pivot_info = f"Pivot: ${pivot:,.4f} | Support 1: ${s1:,.4f} | Resistance 1: ${r1:,.4f}"
    console.print(Panel(pivot_info, title="6️⃣ Pivot Points & Levels", style="cyan"))

    # Candle Pattern
    console.print(Panel(candle_pattern, title="7️⃣ Candlestick Pattern Scanner", style="white"))

    # LOOP PROMPT
    console.print("\n")
    choice = Prompt.ask("[bold yellow]🔄 Kisi aur coin ka analysis karna hai? (Y / N)[/bold yellow]", choices=["y", "n"], default="y")
    return choice.lower() == "y"

def main():
    running = True
    while running:
        running = analyze_coin()

if __name__ == "__main__":
    main()
