import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.prompt import Prompt
from rich.text import Text

console = Console()

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
        return "[bold bright_green]HIGH VOLUME SPIKE ⚡ (STRONG MOMENTUM)[/bold bright_green]", "green"
    return "[bold yellow]NORMAL VOLUME ⚖️[/bold yellow]", "yellow"

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
        return "NEUTRAL ⚖️"
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
        Text("⚡ CRYPTO AI PREDICTION & TECHNICAL TERMINAL ⚡\n👨‍💻 DEVELOPER: BILAL ALI (SHEBI)", justify="center", style="bold cyan"),
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

    console.print(f"\n[bold cyan]🔄 Binance se {coin}/USDT ka live data fetch ho raha hai...[/bold cyan]")
    
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h = get_binance_klines(coin, interval="1h")
    df_4h = get_binance_klines(coin, interval="4h")

    if df_1h is None or df_1h.empty:
        console.print("[bold red]❌ Data fetch nahi ho saka. Symbol verify karein.[/bold red]")
        Prompt.ask("\n[bold yellow]Enter dabayein dobara try karne ke liye...[/bold yellow]")
        return True

    live_price = df_1h['close'].iloc[-1]

    # Indicator Calculations
    rsi = calculate_rsi(df_1h)
    macd_val, macd_sig = calculate_macd(df_1h)
    is_uptrend = calculate_psar(df_1h)
    ema20, sma50 = calculate_ma(df_1h)
    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    vol_txt, vol_color = check_volume_spike(df_1h)
    pivot, s1, s2, r1, r2 = calculate_pivot_points(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    trend_15m = get_tf_trend(df_15m)
    trend_1h = get_tf_trend(df_1h)
    trend_4h = get_tf_trend(df_4h)

    # AI ENGINE LOGIC & PREDICTIONS
    bullish_score = 0
    if rsi < 65 and rsi > 30: bullish_score += 1
    if macd_val > macd_sig: bullish_score += 1
    if is_uptrend: bullish_score += 1
    if live_price > ema20: bullish_score += 1
    if "BULLISH" in trend_1h: bullish_score += 1

    if bullish_score >= 4:
        ai_decision = "[bold green]🚀 BUY ENTRY RECOMMENDED (High Bullish Momentum)[/bold green]"
        ai_target = r1 if r1 > live_price else live_price * 1.035
        ai_sl = s1 if s1 < live_price else live_price * 0.985
        ai_box_style = "bold green"
        ai_reason = "Indicator alignment strong hai. RSI aur MACD safe bullish zone me hain."
    elif bullish_score <= 1 or rsi > 70:
        ai_decision = "[bold red]🛑 NO ENTRY / BEARISH PRESSURE (Risk of Dump)[/bold red]"
        ai_target = live_price * 0.96
        ai_sl = supply_zone * 1.01
        ai_box_style = "bold red"
        ai_reason = "Market overbought hai ya bearish pressure dominant hai. Entry se garez karein."
    else:
        ai_decision = "[bold yellow]⏳ WAIT & WATCH (Market Consolidating)[/bold yellow]"
        ai_target = r1
        ai_sl = s1
        ai_box_style = "bold yellow"
        ai_reason = "Trend confirm nahi hai. Safe entry point ka wait karein."

    target_pct = ((ai_target - live_price) / live_price) * 100
    sl_pct = ((live_price - ai_sl) / live_price) * 100

    # ---------------------------------------------------------
    # SECTION 1: AI MARKET PREDICTION REPORT
    # ---------------------------------------------------------
    console.print("\n")
    console.print(Rule(title=f"[bold cyan]🤖 AI PREDICTION REPORT ({coin}/USDT) | Live Rate: ${live_price:,.4f}[/bold cyan]", style="cyan"))

    ai_report = f"""
📌 [bold white]AI DECISION:[/bold white] {ai_decision}
💡 [bold white]REASON:[/bold white] {ai_reason}

🎯 [bold green]EXPECTED TARGET (Imkan):[/bold green] [bold green]${ai_target:,.4f}[/bold green] ([bold green]{target_pct:+.2f}%[/bold green])
🛑 [bold red]RECOMMENDED STOP LOSS:[/bold red] [bold red]${ai_sl:,.4f}[/bold red] ([bold red]-{sl_pct:.2f}%[/bold red])
🏢 [bold magenta]KEY SUPPLY / DEMAND:[/bold magenta] Demand: ${demand_zone:,.4f} | Supply: ${supply_zone:,.4f}
"""
    console.print(Panel(ai_report, title="[bold cyan]⚡ AI SYSTEM ENGINE ANALYSIS[/bold cyan]", style=ai_box_style))

    # ---------------------------------------------------------
    # SECTION 2: TECHNICAL INDICATORS BREAKDOWN
    # ---------------------------------------------------------
    console.print("\n")
    console.print(Rule(title=f"[bold magenta]📊 TECHNICAL INDICATORS BREAKDOWN[/bold magenta]", style="magenta"))

    # RSI
    rsi_txt = f"RSI Value: {rsi:.2f} | Status: " + ("OVERSOLD 📈" if rsi < 30 else "OVERBOUGHT 📉" if rsi > 70 else "NEUTRAL ⚖️")
    console.print(Panel(rsi_txt, title="1️⃣ RSI (14)", style="green" if rsi < 60 else "red"))

    # MACD
    macd_txt = f"MACD Val: {macd_val:.4f} | Signal: {macd_sig:.4f} -> " + ("BULLISH CROSSOVER 🟢" if macd_val > macd_sig else "BEARISH CROSSOVER 🔴")
    console.print(Panel(macd_txt, title="2️⃣ MACD Indicator", style="green" if macd_val > macd_sig else "red"))

    # PSAR & MA
    ma_txt = f"PSAR: {'UPTREND 📈' if is_uptrend else 'DOWNTREND 📉'} | EMA20: ${ema20:,.4f} | SMA50: ${sma50:,.4f}"
    console.print(Panel(ma_txt, title="3️⃣ PSAR & Moving Averages", style="cyan"))

    # Bollinger & Volume
    vol_bb = f"BB Upper: ${upper_bb:,.4f} | BB Lower: ${lower_bb:,.4f}\nVolume: {vol_txt}"
    console.print(Panel(vol_bb, title="4️⃣ Bollinger Bands & Volume", style="blue"))

    # Timeframe Alignment
    mtf_txt = f"15m: {trend_15m} | 1h: {trend_1h} | 4h: {trend_4h}"
    console.print(Panel(mtf_txt, title="5️⃣ Multi-Timeframe Alignment", style="magenta"))

    # Pattern
    console.print(Panel(candle_pattern, title="6️⃣ Candlestick Pattern", style="white"))

    # LOOP PROMPT
    console.print("\n")
    choice = Prompt.ask("[bold yellow]🔄 Kisi aur coin ka check karna hai? (Y / N)[/bold yellow]", choices=["y", "n"], default="y")
    return choice.lower() == "y"

def main():
    running = True
    while running:
        running = analyze_coin()

if __name__ == "__main__":
    main()
