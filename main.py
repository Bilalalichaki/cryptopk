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
        return "[bold bright_green]HIGH VOLUME SPIKE ⚡[/bold bright_green]"
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
        style="blue"
    )
    console.print(header)

def run_app():
    show_header()
    coin = Prompt.ask("\n[bold yellow]📌 Symbol enter karein (e.g. BTC, ETH, PAXG)[/bold yellow]").upper().strip()
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

    if is_all_bull and macd_val > macd_sig:
        direction = "BUY / LONG 🟢"
        tp_val = live_price * 1.02
        sl_val = live_price * 0.985
    elif is_all_bear and macd_val < macd_sig:
        direction = "SELL / SHORT 🔴"
        tp_val = live_price * 0.98
        sl_val = live_price * 1.015
    else:
        direction = "WAIT / NO TRADE ⚠️"
        tp_val = live_price * 1.015
        sl_val = live_price * 0.99

    # CLEAR SIGNAL CARD (Yellow Entry, Green TP, Red SL)
    signal_box = f"""
[bold yellow]📍 ENTRY RATE:[/bold yellow]  [bold yellow]${live_price:,.4f}[/bold yellow]
[bold green]🎯 TARGET (TP):[/bold green] [bold green]${tp_val:,.4f}[/bold green]
[bold red]🛑 STOP LOSS (SL):[/bold red] [bold red]${sl_val:,.4f}[/bold red]
[bold cyan]📊 SIGNAL DIRECTION:[/bold cyan] [bold white]{direction}[/bold white]
"""
    console.print(Panel(signal_box, title="[bold bright_yellow]⚡ QUICK TRADE SIGNAL SUMMARY ⚡[/bold bright_yellow]", style="magenta"))

    # DETAILED INDICATOR TABLE
    table = Table(title=f"📊 All Technical Indicators ({coin}/USDT)", style="bright_blue", header_style="bold cyan")
    table.add_column("Indicator / Metric", style="cyan")
    table.add_column("Value / Level", style="bold white")
    table.add_column("Signal Status", style="bold yellow")

    table.add_row("RSI (14)", f"{rsi:.2f}", rsi_sig)
    table.add_row("MACD Crossover", f"Val: {macd_val:.2f} | Sig: {macd_sig:.2f}", macd_status)
    table.add_row("Parabolic SAR", "Trend Status", sar_status)
    table.add_row("Moving Averages", f"EMA20: ${ema20:,.2f} | SMA50: ${sma50:,.2f}", ma_status)
    table.add_row("Bollinger Bands", f"Upper: ${upper_bb:,.2f} | Lower: ${lower_bb:,.2f}", bb_status)
    table.add_row("Volume Status", "20-Period Avg", vol_status)
    table.add_row("Pivot Points", f"P: ${pivot:,.2f}", f"S1: ${s1:,.2f} | R1: ${r1:,.2f}")
    table.add_row("Demand/Supply", f"Demand: ${demand_zone:,.2f}", f"Supply: ${supply_zone:,.2f}")
    table.add_row("Multi-Timeframe", f"15m: {trend_15m} | 1h: {trend_1h}", f"4h: {trend_4h}")
    table.add_row("Candle Pattern", candle_pattern, "Pattern Scanner")

    console.print(table)

    # INTERACTIVE POSITION CALCULATOR
    console.print("\n[bold yellow]❓ Trade Risk & Position Calculator chalana chahte hain?[/bold yellow]")
    calc_choice = Prompt.ask("👉 Choice ([1] Haan / [2] Nahi)", choices=["1", "2"], default="1")

    if calc_choice == "1":
        balance = float(Prompt.ask("\n[bold yellow]💵 Aapka Total Capital / Balance ($)[/bold yellow]", default="200"))
        margin = float(Prompt.ask("[bold yellow]💰 Is trade par kitna Margin lagana chahte hain ($)[/bold yellow]", default=str(round(balance * 0.2, 2))))
        leverage = float(Prompt.ask("[bold yellow]⚡ Leverage kitni rakhni hai (e.g. 10, 20, 50)[/bold yellow]", default="20"))
        
        pos_type = Prompt.ask("[bold yellow]📈 Position Type ([1] Long / [2] Short)[/bold yellow]", choices=["1", "2"], default="1")
        is_long = pos_type == "1"

        entry_p = float(Prompt.ask("📍 Entry Price ($)", default=str(round(live_price, 4))))
        exit_p = float(Prompt.ask("🎯 Target Exit (TP) ($)", default=str(round(tp_val, 4))))
        sl_p = float(Prompt.ask("🛑 Stop Loss (SL) ($)", default=str(round(sl_val, 4))))
        pkr_rate = float(Prompt.ask("💱 USD to PKR Rate", default="278.5"))

        position_size = margin * leverage
        coins = position_size / entry_p

        if is_long:
            pnl_usd = (exit_p - entry_p) * coins
            loss_usd = (entry_p - sl_p) * coins
            liq_price = entry_p * (1 - 1 / leverage)
        else:
            pnl_usd = (entry_p - exit_p) * coins
            loss_usd = (sl_p - entry_p) * coins
            liq_price = entry_p * (1 + 1 / leverage)

        roe = (pnl_usd / margin) * 100
        pnl_pkr = pnl_usd * pkr_rate
        loss_pkr = loss_usd * pkr_rate

        calc_summary = f"""
[bold yellow]💼 Account Margin Used:[/bold yellow] [bold white]${margin:,.2f}[/bold white] (Rs. {margin * pkr_rate:,.2f})
[bold yellow]🔍 Position Volume:[/bold yellow]     [bold white]${position_size:,.2f}[/bold white] ({coins:.4f} {coin})
[bold yellow]⚡ Selected Leverage:[/bold yellow]   [bold white]{leverage:.0f}x[/bold white]

[bold green]🚀 EST. PROFIT (PnL):[/bold green]    [bold green]+${pnl_usd:,.2f}[/bold green] (Rs. +{pnl_pkr:,.2f}) | [bold green]ROE: +{roe:.2f}%[/bold green]
[bold red]🛑 EST. LOSS (If SL Hits):[/bold red] [bold red]-${loss_usd:,.2f}[/bold red] (Rs. -{loss_pkr:,.2f})
[bold red]💥 LIQUIDATION PRICE:[/bold red]    [bold red]${liq_price:,.4f}[/bold red]
"""
        console.print(Panel(calc_summary, title="[bold green]📊 PERSONALIZED TRADE ESTIMATION[/bold green]", style="green"))

    console.print("\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]\n")

if __name__ == "__main__":
    run_app()
