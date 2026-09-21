import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
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
        return "[bold green]HIGH VOLUME SPIKE ⚡[/bold green]"
    return "Normal Volume"

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
        return "BULLISH ENGULFING 🚀"
    if p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        return "BEARISH ENGULFING 🔻"
    if lower_wick > (2 * body) and upper_wick < body:
        return "BULLISH HAMMER 🔨"
    if upper_wick > (2 * body) and lower_wick < body:
        return "SHOOTING STAR 💫"
    return "Normal Candle"

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    return recent_df['low'].min(), recent_df['high'].max()

def show_header():
    console.clear()
    header = Panel(
        Text("🚀 CRYPTO & GOLD ALL-IN-ONE PRO DASHBOARD 🚀\n👨‍💻 DEVELOPER: BILAL ALI (SHEBI)", justify="center", style="bold cyan"),
        style="bold blue"
    )
    console.print(header)

def run_app():
    show_header()
    coin = Prompt.ask("\n[bold yellow]📌 Symbol enter karein (e.g. BTC, ETH, PAXG, ZEC)[/bold yellow]").upper().strip()
    if not coin:
        return

    console.print(f"\n[bold cyan]🔄 Binance se {coin} ka live data fetch ho raha hai...[/bold cyan]")
    
    df_15m = get_binance_klines(coin, interval="15m")
    df_1h = get_binance_klines(coin, interval="1h")
    df_4h = get_binance_klines(coin, interval="4h")

    if df_1h is None or df_1h.empty:
        console.print("[bold red]❌ Data fetch nahi ho saka. Symbol verify karein.[/bold red]")
        return

    live_price = df_1h['close'].iloc[-1]
    
    # Indicators Calculation
    rsi = calculate_rsi(df_1h)
    rsi_sig = "[bold green]OVERSOLD 📈[/bold green]" if rsi < 30 else ("[bold red]OVERBOUGHT 📉[/bold red]" if rsi > 70 else "[bold yellow]NEUTRAL ⚖️[/bold yellow]")
    macd_val, macd_sig = calculate_macd(df_1h)
    macd_status = "[bold green]BULLISH CROSSOVER 🟢[/bold green]" if macd_val > macd_sig else "[bold red]BEARISH CROSSOVER 🔴[/bold red]"
    is_uptrend = calculate_psar(df_1h)
    sar_status = "[bold green]UPTREND (BUY) 📈[/bold green]" if is_uptrend else "[bold red]DOWNTREND (SELL) 📉[/bold red]"
    ema20, sma50 = calculate_ma(df_1h)
    ma_status = "[bold green]BULLISH TREND 🚀[/bold green]" if live_price > ema20 > sma50 else "[bold red]BEARISH / WEAK 📉[/bold red]"
    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    bb_status = "[bold red]OVERBOUGHT[/bold red]" if live_price >= upper_bb else ("[bold green]OVERSOLD[/bold green]" if live_price <= lower_bb else "In Channel")
    vol_status = check_volume_spike(df_1h)
    pivot, s1, s2, r1, r2 = calculate_pivot_points(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    trend_15m = get_tf_trend(df_15m)
    trend_1h = get_tf_trend(df_1h)
    trend_4h = get_tf_trend(df_4h)

    is_all_bull = "BULLISH" in trend_15m and "BULLISH" in trend_1h and "BULLISH" in trend_4h
    is_all_bear = "BEARISH" in trend_15m and "BEARISH" in trend_1h and "BEARISH" in trend_4h

    # Signal & Levels Prediction Logic
    if is_all_bull and macd_val > macd_sig:
        signal_text = "HIGH CONFIRMATION BUY / LONG 🚀"
        entry_pred = live_price
        tp_pred = live_price * 1.025
        sl_pred = demand_zone * 0.995 if demand_zone < live_price else live_price * 0.985
    elif is_all_bear and macd_val < macd_sig:
        signal_text = "HIGH CONFIRMATION SELL / SHORT 🚨"
        entry_pred = live_price
        tp_pred = live_price * 0.975
        sl_pred = supply_zone * 1.005 if supply_zone > live_price else live_price * 1.015
    else:
        signal_text = "WAIT / NO TRADE (Mixed Signals) ⚠️"
        entry_pred = live_price
        tp_pred = live_price * 1.015
        sl_pred = live_price * 0.99

    # SECTION 1: COLOR-CODED PREDICTION CARDS (SEPARATE BOXES)
    console.print("\n[bold cyan]------------------ 🎯 PREDICTION SIGNALS ------------------[/bold cyan]")
    
    console.print(Panel(
        f"[bold white]PRICE:[/bold white] [bold yellow]${entry_pred:,.4f}[/bold yellow]\n[bold white]Note:[/bold white] Live Market Rate par Entry leni hai.",
        title="[bold yellow]🟡 SAFE ENTRY PREDICTION[/bold yellow]",
        style="yellow"
    ))

    console.print(Panel(
        f"[bold white]TARGET RATE:[/bold white] [bold green]${tp_pred:,.4f}[/bold green]\n[bold white]Note:[/bold white] Yahan profit book karke exit karein.",
        title="[bold green]🟢 TAKE PROFIT (TP) PREDICTION[/bold green]",
        style="green"
    ))

    console.print(Panel(
        f"[bold white]STOP LOSS RATE:[/bold white] [bold red]${sl_pred:,.4f}[/bold red]\n[bold white]Note:[/bold white] Trade galat jaane par yahan auto-close ho.",
        title="[bold red]🔴 STOP LOSS (SL) PREDICTION[/bold red]",
        style="red"
    ))

    console.print(Panel(
        f"[bold cyan]OVERALL SIGNAL:[/bold cyan] [bold white]{signal_text}[/bold white]",
        title="[bold blue]⚡ FINAL DIRECTION[/bold blue]",
        style="cyan"
    ))

    # SECTION 2: ALL TECHNICAL INDICATORS TABLE (SEPARATE SECTION)
    table = Table(title=f"📊 COMPLETE INDICATORS DASHBOARD ({coin}/USDT)", style="magenta", header_style="bold cyan")
    table.add_column("Indicator Name", style="cyan")
    table.add_column("Current Value / Range", style="bold white")
    table.add_column("Signal Status", style="bold yellow")

    table.add_row("Live Price", f"${live_price:,.4f}", "[bold white]Live[/bold white]")
    table.add_row("RSI (14)", f"{rsi:.2f}", rsi_sig)
    table.add_row("MACD Crossover", f"Val: {macd_val:.2f} | Sig: {macd_sig:.2f}", macd_status)
    table.add_row("Parabolic SAR", "Trend Direction", sar_status)
    table.add_row("Moving Averages", f"EMA20: ${ema20:,.2f} | SMA50: ${sma50:,.2f}", ma_status)
    table.add_row("Bollinger Bands", f"Upper: ${upper_bb:,.2f} | Lower: ${lower_bb:,.2f}", bb_status)
    table.add_row("Volume Status", "20-Bar Volume", vol_status)
    table.add_row("Pivot Level (P)", f"${pivot:,.4f}", "Central Pivot")
    table.add_row("Support Levels", f"S1: ${s1:,.2f} | S2: ${s2:,.2f}", "[bold green]BUY AREA[/bold green]")
    table.add_row("Resistance Levels", f"R1: ${r1:,.2f} | R2: ${r2:,.2f}", "[bold red]SELL AREA[/bold red]")
    table.add_row("Demand Zone (Support)", f"${demand_zone:,.4f}", "[bold green]STRONG SUPPORT[/bold green]")
    table.add_row("Supply Zone (Resistance)", f"${supply_zone:,.4f}", "[bold red]STRONG RESISTANCE[/bold red]")
    table.add_row("15-Min Trend", trend_15m, "Scalp Trend")
    table.add_row("1-Hour Trend", trend_1h, "Main Trend")
    table.add_row("4-Hour Trend", trend_4h, "Major Trend")
    table.add_row("Candle Pattern", candle_pattern, "Pattern Scanner")

    console.print("\n", table)

    # SECTION 3: SPOT & FUTURE TRADE CALCULATOR (PURANA SPOT BHI SHAMIL HAI)
    console.print("\n[bold green]2️⃣ Trade Type Select Karein:[/bold green]")
    console.print(" [1] Spot Trading 🛒")
    console.print(" [2] Future Trading ⚡")
    trade_type = Prompt.ask("👉 Choice (1 ya 2)", choices=["1", "2"], default="1")

    is_future = trade_type == "2"
    is_long = True
    leverage = 1.0

    if is_future:
        pos = Prompt.ask("Position Type ([1] Long / [2] Short)", choices=["1", "2"], default="1")
        is_long = pos == "1"
        leverage = float(Prompt.ask("Leverage (e.g. 10, 20, 50)", default="10"))

    entry_price = float(Prompt.ask("Entry Rate ($)", default=str(round(entry_pred, 4))))
    margin = float(Prompt.ask("Investment / Margin ($)", default="100"))
    exit_price = float(Prompt.ask("Target Exit Rate ($)", default=str(round(tp_pred, 4))))
    pkr_rate = float(Prompt.ask("USD to PKR Rate", default="278.5"))
    sl_price = float(Prompt.ask("Stop Loss Rate ($)", default=str(round(sl_pred, 4))))

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
📌 Type: [bold white]{type_str}[/bold white]
🏷️ Entry: [bold yellow]${entry_price:,.4f}[/bold yellow] | Target Exit: [bold green]${exit_price:,.4f}[/bold green]
🛑 Stop Loss: [bold red]${sl_price:,.4f}[/bold red] (Est. Loss: -${loss_usd:.2f} / -Rs. {loss_pkr:,.2f})

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
        summary += f"💥 Est. Liquidation Price: [bold red]${liq_price:,.4f}[/bold red]\n"

    console.print(Panel(summary, title="[bold green]📊 FINAL TRADE CALCULATION[/bold green]", style="green"))
    console.print("\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]\n")

if __name__ == "__main__":
    run_app()
