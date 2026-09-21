import requests
import pandas as pd
import pandas_ta as ta
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

def calculate_technical_indicators(df):
    """RSI, MACD, Parabolic SAR, EMA 20, aur SMA 50 calculate karta hai."""
    # RSI (14)
    df['RSI'] = ta.rsi(df['close'], length=14)
    
    # MACD (12, 26, 9)
    macd_df = ta.macd(df['close'], fast=12, slow=26, signal=9)
    df = pd.concat([df, macd_df], axis=1)
    
    # Parabolic SAR
    psar_df = ta.psar(df['high'], df['low'], df['close'])
    df = pd.concat([df, psar_df], axis=1)
    
    # Moving Averages
    df['EMA_20'] = ta.ema(df['close'], length=20)
    df['SMA_50'] = ta.sma(df['close'], length=50)
    
    return df

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    demand_zone = recent_df['low'].min()
    supply_zone = recent_df['high'].max()
    return demand_zone, supply_zone

def show_header():
    console.clear()
    header_text = "[bold cyan]🚀 CRYPTO ESTIMATOR & MULTI-INDICATOR DASHBOARD 🚀[/bold cyan]\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]"
    console.print(Panel(header_text, style="bold blue", expand=False))

def run_app():
    show_header()
    
    coin = Prompt.ask("\n[bold green]1️⃣ Coin Symbol enter karein (e.g. BTC, ETH, SOL)[/bold green]").upper().strip()
    if not coin:
        return

    console.print(f"\n[yellow]🔄 Binance se {coin} ka live data, MACD, SAR, MA & Zones fetch ho rahe hain...[/yellow]")
    df = get_binance_klines(coin)

    if df is None or df.empty:
        console.print("[bold red]❌ Price fetch nahi ho saka. Valid USDT pair enter karein.[/bold red]")
        return

    df = calculate_technical_indicators(df)
    live_price = df['close'].iloc[-1]
    demand_zone, supply_zone = detect_supply_demand_zones(df)

    # 1. RSI Signal
    rsi = df['RSI'].iloc[-1]
    rsi_signal = "[bold yellow]NEUTRAL ⚖️[/bold yellow]"
    if rsi < 30:
        rsi_signal = "[bold green]OVERSOLD / BUY ZONE 📈[/bold green]"
    elif rsi > 70:
        rsi_signal = "[bold red]OVERBOUGHT / SELL ZONE 📉[/bold red]"

    # 2. MACD Signal
    macd_val = df['MACD_12_26_9'].iloc[-1]
    macd_sig = df['MACDs_12_26_9'].iloc[-1]
    macd_signal = "[bold green]BULLISH CROSSOVER 🟢[/bold green]" if macd_val > macd_sig else "[bold red]BEARISH CROSSOVER 🔴[/bold red]"

    # 3. Parabolic SAR Signal
    psar_long = df['PSARl_0.02_0.2'].iloc[-1]
    sar_signal = "[bold green]UPTREND (BUY) 📈[/bold green]" if not pd.isna(psar_long) else "[bold red]DOWNTREND (SELL) 📉[/bold red]"

    # 4. Moving Averages Signal
    ema20 = df['EMA_20'].iloc[-1]
    sma50 = df['SMA_50'].iloc[-1]
    ma_trend = "[bold green]BULLISH (Price > EMA20 > SMA50) 🚀[/bold green]" if live_price > ema20 > sma50 else "[bold red]BEARISH / WEAK TREND 📉[/bold red]"

    # Display Analysis Table
    table = Table(title=f"📊 Pro Technical Analysis: {coin}/USDT", style="magenta")
    table.add_column("Indicator / Metric", style="cyan")
    table.add_column("Value / Level", style="bold white")
    table.add_column("Signal Status", style="bold yellow")

    table.add_row("Live Price", f"${live_price:,.4f}", "[bold white]Live[/bold white]")
    table.add_row("RSI (14)", f"{rsi:.2f}", rsi_signal)
    table.add_row("MACD Crossover", f"Val: {macd_val:.2f} | Sig: {macd_sig:.2f}", macd_signal)
    table.add_row("Parabolic SAR", f"SAR Level", sar_signal)
    table.add_row("Moving Averages", f"EMA20: ${ema20:,.2f} | SMA50: ${sma50:,.2f}", ma_trend)
    table.add_row("Demand Zone (Support)", f"${demand_zone:,.4f}", "[bold green]BUY AREA[/bold green]")
    table.add_row("Supply Zone (Resistance)", f"${supply_zone:,.4f}", "[bold red]SELL AREA[/bold red]")

    console.print("\n", table)

    # Calculation Section
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
