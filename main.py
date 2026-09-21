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

def detect_supply_demand_zones(df):
    recent_df = df.tail(30)
    demand_zone = recent_df['low'].min()
    supply_zone = recent_df['high'].max()
    return demand_zone, supply_zone

def show_header():
    console.clear()
    header_text = "[bold cyan]🚀 CRYPTO ESTIMATOR & TECHNICAL DASHBOARD 🚀[/bold cyan]\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]"
    console.print(Panel(header_text, style="bold blue", expand=False))

def run_app():
    show_header()
    
    # Coin Selection
    coin = Prompt.ask("\n[bold green]1️⃣ Coin Symbol enter karein (e.g. BTC, ETH, SOL)[/bold green]").upper().strip()
    if not coin:
        return

    console.print(f"\n[yellow]🔄 Binance se {coin} ka live data, RSI aur Supply/Demand Zones fetch ho rahe hain...[/yellow]")
    df = get_binance_klines(coin)

    if df is None or df.empty:
        console.print("[bold red]❌ Price fetch nahi ho saka. Valid USDT pair enter karein.[/bold red]")
        return

    live_price = df['close'].iloc[-1]
    rsi = calculate_rsi(df)
    demand_zone, supply_zone = detect_supply_demand_zones(df)

    signal = "[bold yellow]NEUTRAL ⚖️[/bold yellow]"
    if rsi < 30:
        signal = "[bold green]OVERSOLD / BUY ZONE 📈[/bold green]"
    elif rsi > 70:
        signal = "[bold red]OVERBOUGHT / SELL ZONE 📉[/bold red]"

    # Market Analysis Table
    table = Table(title=f"📊 Market Analysis: {coin}/USDT", style="magenta")
    table.add_column("Indicator / Metric", style="cyan")
    table.add_column("Value / Level", style="bold white")

    table.add_row("Live Market Price", f"${live_price:,.4f}")
    table.add_row("RSI (14)", f"{rsi:.2f}")
    table.add_row("Market Condition", signal)
    table.add_row("Demand Zone (Support)", f"${demand_zone:,.4f}")
    table.add_row("Supply Zone (Resistance)", f"${supply_zone:,.4f}")

    console.print("\n", table)

    # Trading Inputs
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

    # Calculations
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

    # Output Display
    summary = f"""
[bold yellow]--- TRADE ESTIMATION RESULTS ---[/bold yellow]
📌 Type: [bold white]{'Future ' + ('LONG' if is_long else 'SHORT') if is_future else 'SPOT'}[/bold white] | Leverage: [bold white]{leverage}x[/bold white]
🏷️ Entry: [bold white]${entry_price:,.2f}[/bold white] | Target Exit: [bold white]${exit_price:,.2f}[/bold white]
🛑 Stop Loss: [bold red]${sl_price:,.2f}[/bold red] (Est. Loss: -${loss_usd:.2f} / -Rs. {loss_pkr:,.2f})

💰 Capital Margin: [bold white]${margin:,.2f}[/bold white] (Rs. {margin * pkr_rate:,.2f})
🔍 Position Volume: [bold white]${position_size:,.2f}[/bold white] ({coins:.4f} {coin})

🚀 Estimated Profit (PnL): [bold green]+${pnl_usd:.2f}[/bold green] (Rs. [bold green]+{pnl_pkr:,.2f}[/bold green])
📊 Return on Margin (ROE): [bold green]+{roe:.2f}%[/bold green]
⚖️ Risk to Reward Ratio: [bold cyan]1 : {risk_reward:.2f}[/bold cyan]
"""
    if is_future:
        summary += f"\n💥 Est. Liquidation Price: [bold red]${liq_price:,.2f}[/bold red]"

    console.print(Panel(summary, title="[bold green]Final Calculation[/bold green]", style="green"))
    console.print("\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]\n")

if __name__ == "__main__":
    run_app()
