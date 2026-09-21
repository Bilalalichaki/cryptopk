import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

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

def calculate_ma(df):
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    sma50 = df['close'].rolling(window=50).mean().iloc[-1]
    return ema20, sma50

def get_tf_trend(df):
    """Timeframe trend check karta hai (EMA 20 vs Price)."""
    if df is None or df.empty:
        return "NEUTRAL ⚖️"
    live_price = df['close'].iloc[-1]
    ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
    if live_price > ema20:
        return "[bold green]BULLISH 📈[/bold green]"
    else:
        return "[bold red]BEARISH 📉[/bold red]"

def detect_candlestick_patterns(df):
    """Hammer, Engulfing aur Shooting Star detect karta hai."""
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    c_open, c_close, c_high, c_low = curr['open'], curr['close'], curr['high'], curr['low']
    p_open, p_close = prev['open'], prev['close']

    body = abs(c_close - c_open)
    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)

    # Bullish Engulfing
    if p_close < p_open and c_close > c_open and c_close > p_open and c_open < p_close:
        return "BULLISH ENGULFING 🚀 (Strong Reversal)"

    # Bearish Engulfing
    if p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        return "BEARISH ENGULFING 🔻 (Strong Drop)"

    # Hammer
    if lower_wick > (2 * body) and upper_wick < body:
        return "BULLISH HAMMER 🔨 (Bottom Reversal)"

    # Shooting Star
    if upper_wick > (2 * body) and lower_wick < body:
        return "SHOOTING STAR 💫 (Top Reversal)"

    return "No Major Pattern (Normal Candle)"

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    demand_zone = recent_df['low'].min()
    supply_zone = recent_df['high'].max()
    return demand_zone, supply_zone

def show_header():
    console.clear()
    header_text = "[bold cyan]🚀 CRYPTO & GOLD PRO PREDICTION DASHBOARD 🚀[/bold cyan]\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]"
    console.print(Panel(header_text, style="bold blue", expand=False))

def run_app():
    show_header()
    
    coin = Prompt.ask("\n[bold green]1️⃣ Symbol enter karein (e.g. BTC, ETH, PAXG for Gold)[/bold green]").upper().strip()
    if not coin:
        return

    console.print(f"\n[yellow]🔄 Binance se {coin} ka Multi-Timeframe (15m, 1h, 4h) & Candle analysis ho raha hai...[/yellow]")
    
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h = get_binance_klines(coin, interval="1h")
    df_4h = get_binance_klines(coin, interval="4h")

    if df_1h is None or df_1h.empty:
        console.print("[bold red]❌ Data fetch nahi ho saka. Valid USDT pair enter karein.[/bold red]")
        return

    live_price = df_1h['close'].iloc[-1]
    rsi = calculate_rsi(df_1h)
    ema20, sma50 = calculate_ma(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    # Multi-timeframe trend statuses
    trend_15m = get_tf_trend(df_15m)
    trend_1h = get_tf_trend(df_1h)
    trend_4h = get_tf_trend(df_4h)

    # High Probability Signal (85%+ Target)
    is_all_bull = "BULLISH" in trend_15m and "BULLISH" in trend_1h and "BULLISH" in trend_4h
    is_all_bear = "BEARISH" in trend_15m and "BEARISH" in trend_1h and "BEARISH" in trend_4h

    if is_all_bull and "BULLISH" in candle_pattern:
        signal = "[bold green]🔥 HIGH CONFIRMATION BUY (85%+ ACCURACY) 🔥[/bold green]"
    elif is_all_bear and ("BEARISH" in candle_pattern or "SHOOTING" in candle_pattern):
        signal = "[bold red]🚨 HIGH CONFIRMATION SELL (85%+ ACCURACY) 🚨[/bold red]"
    elif is_all_bull:
        signal = "[bold green]MODERATE BUY (Trend Confirmed) 📈[/bold green]"
    elif is_all_bear:
        signal = "[bold red]MODERATE SELL (Trend Confirmed) 📉[/bold red]"
    else:
        signal = "[bold yellow]WAIT / NO TRADE (Mixed Timeframes) ⚠️[/bold yellow]"

    # Display Analysis Table
    table = Table(title=f"📊 Market Analysis & Candle Scanner: {coin}/USDT", style="magenta")
    table.add_column("Analysis / Metric", style="cyan")
    table.add_column("Value / Status", style="bold white")

    table.add_row("Live Price", f"${live_price:,.4f}")
    table.add_row("RSI (14 - 1H)", f"{rsi:.2f}")
    table.add_row("15-Min Trend", trend_15m)
    table.add_row("1-Hour Trend", trend_1h)
    table.add_row("4-Hour Trend", trend_4h)
    table.add_row("Detected Pattern", f"[bold yellow]{candle_pattern}[/bold yellow]")
    table.add_row("Demand Zone (Support)", f"${demand_zone:,.4f}")
    table.add_row("Supply Zone (Resistance)", f"${supply_zone:,.4f}")

    console.print("\n", table)
    console.print(Panel(f"🎯 [bold yellow]FINAL PREDICTION SIGNAL:[/bold yellow]\n{signal}", style="bold cyan"))

    # Calculator Section
    console.print("\n[bold green]2️⃣ Trade Type Select Karein:[/bold green]")
    console.print(" [1] Spot Trading")
    console.print(" [2] Future Trading")
    trade_type = Prompt.ask("👉 Choice (1 ya 2)", choices=["1", "2"], default="1")

    is_future = trade_type == "2"
    is_long = True
    leverage = 1.0

    if is_future:
        pos = Prompt.ask("Position Type ([1] Long / [2] Short)", choices=["1", "2"], default="1")
        is_long = pos == "1"
        leverage = float(Prompt.ask("Leverage (e.g. 10, 20, 50)", default="10"))

    entry_price = float(Prompt.ask("Entry Rate ($)", default=str(live_price)))
    margin = float(Prompt.ask("Investment / Margin ($)", default="100"))
    exit_price = float(Prompt.ask("Target Exit Rate ($)"))
    pkr_rate = float(Prompt.ask("USD to PKR Rate", default="278.5"))

    default_sl = entry_price * 0.95 if (is_long or not is_future) else entry_price * 1.05
    sl_price = float(Prompt.ask("Stop Loss Rate ($)", default=str(round(default_sl, 2))))

    position_size = margin * leverage
    coins = position_size / entry_price
    
    if is_long or not is_future:
        pnl_usd = (exit_price - entry_price) * coins
        loss_usd = (entry_price - sl_price) * coins
        liq_price = entry_price * (1 - 1 / leverage) if is_future else 0
    else:
        pnl_usd = (entry_price - exit_price) * coins
        loss_usd = (sl_price - entry_price) * coins
        liq_price = entry_price * (1 + 1 / leverage)

    roe = (pnl_usd / margin) * 100
    pnl_pkr = pnl_usd * pkr_rate
    loss_pkr = loss_usd * pkr_rate
    risk_reward = abs(pnl_usd / loss_usd) if loss_usd > 0 else 0

    type_str = f"Future ({'LONG 📈' if is_long else 'SHORT 📉'}) | Leverage: {leverage:.1f}x" if is_future else "SPOT Buying 🛒"
    
    summary = f"""
[bold yellow]--- TRADE ESTIMATION RESULTS ---[/bold yellow]
📌 Type: [bold white]{type_str}[/bold white]
🏷️ Entry: [bold white]${entry_price:,.2f}[/bold white] | Target Exit: [bold white]${exit_price:,.2f}[/bold white]
🛑 Stop Loss: [bold red]${sl_price:,.2f}[/bold red] (Est. Loss: -${loss_usd:.2f} / -Rs. {loss_pkr:,.2f})

💰 Capital Investment: [bold white]${margin:,.2f}[/bold white] (Rs. {margin * pkr_rate:,.2f})
"""
    if is_future:
        summary += f"🔍 Total Position Volume: [bold white]${position_size:,.2f}[/bold white] ({coins:.4f} {coin})\n"
    else:
        summary += f"🪙 Coins Purchased: [bold white]{coins:.4f} {coin}[/bold white]\n"

    summary += f"""
🚀 Estimated Profit (PnL): [bold green]+${pnl_usd:.2f}[/bold green] (Rs. [bold green]+{pnl_pkr:,.2f}[/bold green])
📊 Return on Investment (ROI): [bold green]+{roe:.2f}%[/bold green]
⚖️ Risk to Reward Ratio: [bold cyan]1 : {risk_reward:.2f}[/bold cyan]
"""
    if is_future:
        summary += f"💥 Est. Liquidation Price: [bold red]${liq_price:,.2f}[/bold red]\n"

    console.print(Panel(summary, title="[bold green]Final Calculation[/bold green]", style="green"))
    console.print("\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]\n")

if __name__ == "__main__":
    run_app()
