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
        return "[bold bright_green]HIGH VOLUME SPIKE ⚡ (BULLISH MOMENTUM)[/bold bright_green]", "green"
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
        return "[bold yellow]NEUTRAL ⚖️[/bold yellow]"
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
        Text("⚡ CRYPTO PURE TECHNICAL INDICATORS TERMINAL ⚡\n👨‍💻 DEVELOPER: BILAL ALI (SHEBI)", justify="center", style="bold cyan"),
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
    if rsi < 30:
        rsi_txt = f"[bold green]RSI: {rsi:.2f} -> OVERSOLD 📈 (BUY ZONE)[/bold green]"
        rsi_color = "green"
    elif rsi > 70:
        rsi_txt = f"[bold red]RSI: {rsi:.2f} -> OVERBOUGHT 📉 (SELL ZONE)[/bold red]"
        rsi_color = "red"
    else:
        rsi_txt = f"[bold yellow]RSI: {rsi:.2f} -> NEUTRAL ⚖️[/bold yellow]"
        rsi_color = "yellow"

    macd_val, macd_sig = calculate_macd(df_1h)
    if macd_val > macd_sig:
        macd_txt = f"[bold green]Val: {macd_val:.4f} | Sig: {macd_sig:.4f} -> BULLISH CROSSOVER 🟢[/bold green]"
        macd_color = "green"
    else:
        macd_txt = f"[bold red]Val: {macd_val:.4f} | Sig: {macd_sig:.4f} -> BEARISH CROSSOVER 🔴[/bold red]"
        macd_color = "red"

    is_uptrend = calculate_psar(df_1h)
    psar_txt = "[bold green]UPTREND 📈 (BULLISH)[/bold green]" if is_uptrend else "[bold red]DOWNTREND 📉 (BEARISH)[/bold red]"
    psar_color = "green" if is_uptrend else "red"

    ema20, sma50 = calculate_ma(df_1h)
    if live_price > ema20 > sma50:
        ma_txt = f"[bold green]EMA20 (${ema20:,.4f}) > SMA50 (${sma50:,.4f}) -> STRONG BULLISH 🚀[/bold green]"
        ma_color = "green"
    else:
        ma_txt = f"[bold red]EMA20 (${ema20:,.4f}) < SMA50 (${sma50:,.4f}) -> WEAK / BEARISH 📉[/bold red]"
        ma_color = "red"

    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    bb_txt = f"Upper Band: [bold red]${upper_bb:,.4f}[/bold red] | Lower Band: [bold green]${lower_bb:,.4f}[/bold green]"
    
    vol_txt, vol_color = check_volume_spike(df_1h)
    pivot, s1, s2, r1, r2 = calculate_pivot_points(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    trend_15m = get_tf_trend(df_15m)
    trend_1h = get_tf_trend(df_1h)
    trend_4h = get_tf_trend(df_4h)

    # OUTPUT SECTION - ONLY INDICATORS
    console.print("\n")
    console.print(Rule(title=f"[bold magenta]📊 ALL INDICATORS BREAKDOWN ({coin}/USDT) | Live Price: ${live_price:,.4f}[/bold magenta]", style="magenta"))

    # 1. RSI
    console.print(Panel(rsi_txt, title="[bold cyan]1️⃣ RSI (14) Indicator[/bold cyan]", style=rsi_color))
    console.print(Rule(style="dim white"))

    # 2. MACD
    console.print(Panel(macd_txt, title="[bold cyan]2️⃣ MACD Indicator[/bold cyan]", style=macd_color))
    console.print(Rule(style="dim white"))

    # 3. PSAR
    console.print(Panel(psar_txt, title="[bold cyan]3️⃣ Parabolic SAR[/bold cyan]", style=psar_color))
    console.print(Rule(style="dim white"))

    # 4. MA
    console.print(Panel(ma_txt, title="[bold cyan]4️⃣ Moving Averages (EMA20 vs SMA50)[/bold cyan]", style=ma_color))
    console.print(Rule(style="dim white"))

    # 5. BB
    console.print(Panel(bb_txt, title="[bold cyan]5️⃣ Bollinger Bands Range[/bold cyan]", style="blue"))
    console.print(Rule(style="dim white"))

    # 6. Volume
    console.print(Panel(vol_txt, title="[bold cyan]6️⃣ Volume Analysis[/bold cyan]", style=vol_color))
    console.print(Rule(style="dim white"))

    # 7. Pivots
    pivot_info = f"""
[bold white]Pivot Point (P):[/bold white] ${pivot:,.4f}
[bold green]Support 1 (S1):[/bold green] ${s1:,.4f}  |  [bold green]Support 2 (S2):[/bold green] ${s2:,.4f}
[bold red]Resistance 1 (R1):[/bold red] ${r1:,.4f}  |  [bold red]Resistance 2 (R2):[/bold red] ${r2:,.4f}
"""
    console.print(Panel(pivot_info, title="[bold cyan]7️⃣ Pivot Points & Key Levels[/bold cyan]", style="cyan"))
    console.print(Rule(style="dim white"))

    # 8. Demand/Supply
    ds_info = f"""
[bold green]🟢 Demand Zone (Support Area):[/bold green] ${demand_zone:,.4f}
[bold red]🔴 Supply Zone (Resistance Area):[/bold red] ${supply_zone:,.4f}
"""
    console.print(Panel(ds_info, title="[bold cyan]8️⃣ Demand & Supply Zones[/bold cyan]", style="magenta"))
    console.print(Rule(style="dim white"))

    # 9. MTF Trend
    mtf_info = f"15m: {trend_15m} | 1h: {trend_1h} | 4h: {trend_4h}"
    console.print(Panel(mtf_info, title="[bold cyan]9️⃣ Multi-Timeframe Trend[/bold cyan]", style="blue"))
    console.print(Rule(style="dim white"))

    # 10. Candle Pattern
    console.print(Panel(candle_pattern, title="[bold cyan]🔟 Candlestick Pattern Scanner[/bold cyan]", style="white"))

    # REPEAT PROMPT
    console.print("\n")
    choice = Prompt.ask("[bold yellow]🔄 Kisi aur coin ka indicator dekhna hai? (Y / N)[/bold yellow]", choices=["y", "n"], default="y")
    return choice.lower() == "y"

def main():
    running = True
    while running:
        running = analyze_coin()

if __name__ == "__main__":
    main()
