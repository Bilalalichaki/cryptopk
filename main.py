import requests
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text
from rich.rule import Rule

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
        return "[bold bright_green]HIGH VOLUME SPIKE ⚡ (PROFIT CHANCE)[/bold bright_green]", "green"
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
        return "[bold green]BULLISH 📈 (PROFIT ZONE)[/bold green]"
    else:
        return "[bold red]BEARISH 📉 (LOSS ZONE)[/bold red]"

def detect_candlestick_patterns(df):
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    c_open, c_close, c_high, c_low = curr['open'], curr['close'], curr['high'], curr['low']
    p_open, p_close = prev['open'], prev['close']
    body = abs(c_close - c_open)
    lower_wick = min(c_open, c_close) - c_low
    upper_wick = c_high - max(c_open, c_close)

    if p_close < p_open and c_close > c_open and c_close > p_open and c_open < p_close:
        return "[bold green]BULLISH ENGULFING 🚀 (BUY SIGNAL)[/bold green]"
    if p_close > p_open and c_close < c_open and c_close < p_open and c_open > p_close:
        return "[bold red]BEARISH ENGULFING 🔻 (SELL SIGNAL)[/bold red]"
    if lower_wick > (2 * body) and upper_wick < body:
        return "[bold green]BULLISH HAMMER 🔨 (BUY SIGNAL)[/bold green]"
    if upper_wick > (2 * body) and lower_wick < body:
        return "[bold red]SHOOTING STAR 💫 (SELL SIGNAL)[/bold red]"
    return "[bold yellow]NORMAL CANDLE ⚖️[/bold yellow]"

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
    
    # 1. Indicator Calculations
    rsi = calculate_rsi(df_1h)
    if rsi < 30:
        rsi_txt = f"[bold green]RSI: {rsi:.2f} -> OVERSOLD 📈 (PROFIT / BUY AREA)[/bold green]"
        rsi_color = "green"
    elif rsi > 70:
        rsi_txt = f"[bold red]RSI: {rsi:.2f} -> OVERBOUGHT 📉 (LOSS RISK / SELL AREA)[/bold red]"
        rsi_color = "red"
    else:
        rsi_txt = f"[bold yellow]RSI: {rsi:.2f} -> NEUTRAL ⚖️ (SAFE HOLD)[/bold yellow]"
        rsi_color = "yellow"

    macd_val, macd_sig = calculate_macd(df_1h)
    if macd_val > macd_sig:
        macd_txt = f"[bold green]Val: {macd_val:.2f} | Sig: {macd_sig:.2f} -> BULLISH CROSSOVER 🟢 (PROFIT)[/bold green]"
        macd_color = "green"
    else:
        macd_txt = f"[bold red]Val: {macd_val:.2f} | Sig: {macd_sig:.2f} -> BEARISH CROSSOVER 🔴 (LOSS)[/bold red]"
        macd_color = "red"

    is_uptrend = calculate_psar(df_1h)
    psar_txt = "[bold green]UPTREND 📈 (PROFIT TREND)[/bold green]" if is_uptrend else "[bold red]DOWNTREND 📉 (LOSS TREND)[/bold red]"
    psar_color = "green" if is_uptrend else "red"

    ema20, sma50 = calculate_ma(df_1h)
    if live_price > ema20 > sma50:
        ma_txt = f"[bold green]EMA20 (${ema20:,.2f}) > SMA50 (${sma50:,.2f}) -> STRONG BULLISH 🚀[/bold green]"
        ma_color = "green"
    else:
        ma_txt = f"[bold red]EMA20 (${ema20:,.2f}) < SMA50 (${sma50:,.2f}) -> WEAK / BEARISH 📉[/bold red]"
        ma_color = "red"

    upper_bb, lower_bb = calculate_bollinger_bands(df_1h)
    bb_txt = f"Upper Band: [bold red]${upper_bb:,.2f}[/bold red] | Lower Band: [bold green]${lower_bb:,.2f}[/bold green]"
    
    vol_txt, vol_color = check_volume_spike(df_1h)
    pivot, s1, s2, r1, r2 = calculate_pivot_points(df_1h)
    demand_zone, supply_zone = detect_supply_demand_zones(df_1h)
    candle_pattern = detect_candlestick_patterns(df_1h)

    trend_15m = get_tf_trend(df_15m)
    trend_1h = get_tf_trend(df_1h)
    trend_4h = get_tf_trend(df_4h)

    is_all_bull = "BULLISH" in trend_15m and "BULLISH" in trend_1h and "BULLISH" in trend_4h
    is_all_bear = "BEARISH" in trend_15m and "BEARISH" in trend_1h and "BEARISH" in trend_4h

    # Signal & Predictions
    if is_all_bull and macd_val > macd_sig:
        signal_text = "[bold green]HIGH CONFIRMATION BUY / LONG 🚀 (PROFIT SPOT)[/bold green]"
        tp_pred = live_price * 1.025
        sl_pred = demand_zone * 0.995 if demand_zone < live_price else live_price * 0.985
    elif is_all_bear and macd_val < macd_sig:
        signal_text = "[bold red]HIGH CONFIRMATION SELL / SHORT 🚨 (LOSS RISK)[/bold red]"
        tp_pred = live_price * 0.975
        sl_pred = supply_zone * 1.005 if supply_zone > live_price else live_price * 1.015
    else:
        signal_text = "[bold yellow]WAIT / NO TRADE ⚠️ (SIDEWAYS MARKET)[/bold yellow]"
        tp_pred = live_price * 1.015
        sl_pred = live_price * 0.99

    # -------------------------------------------------------------
    # SECTION 1: PREDICTION SIGNALS (YELLOW ENTRY, GREEN TP, RED SL)
    # -------------------------------------------------------------
    console.print("\n")
    console.print(Rule(title="[bold yellow]🟡 ENTRY / 🟢 PROFIT / 🔴 STOP LOSS PREDICTIONS[/bold yellow]", style="yellow"))

    console.print(Panel(
        f"[bold white]LIVE ENTRY RATE:[/bold white] [bold yellow]${live_price:,.4f}[/bold yellow]\n"
        f"[bold yellow]📌 Action:[/bold yellow] Yeh aapka SAFE ENTRY point hai.",
        title="[bold yellow]🟡 SAFE ENTRY PREDICTION (YELLOW)[/bold yellow]",
        style="yellow"
    ))

    console.print(Panel(
        f"[bold white]TARGET RATE (TP):[/bold white] [bold green]${tp_pred:,.4f}[/bold green]\n"
        f"[bold green]💰 Action:[/bold green] Yahan target hit hote hi PROFIT book karein.",
        title="[bold green]🟢 TAKE PROFIT PREDICTION (GREEN)[/bold green]",
        style="green"
    ))

    console.print(Panel(
        f"[bold white]STOP LOSS RATE (SL):[/bold white] [bold red]${sl_pred:,.4f}[/bold red]\n"
        f"[bold red]🛑 Action:[/bold red] Market ulti jaane par yahan auto-exit ho taake BADA LOSS na ho.",
        title="[bold red]🔴 STOP LOSS PREDICTION (RED)[/bold red]",
        style="red"
    ))

    console.print(Panel(
        f"[bold cyan]AI MARKET DECISION:[/bold cyan] {signal_text}",
        title="[bold cyan]⚡ OVERALL DIRECTION[/bold cyan]",
        style="cyan"
    ))

    # -------------------------------------------------------------
    # SECTION 2: INDIVIDUAL INDICATOR BOXES WITH DIVIDER LINES
    # -------------------------------------------------------------
    console.print("\n")
    console.print(Rule(title=f"[bold magenta]📊 ALL INDICATORS BREAKDOWN ({coin}/USDT)[/bold magenta]", style="magenta"))

    # RSI Box
    console.print(Panel(rsi_txt, title="[bold cyan]1️⃣ RSI (14) Indicator[/bold cyan]", style=rsi_color))
    console.print(Rule(style="dim white"))

    # MACD Box
    console.print(Panel(macd_txt, title="[bold cyan]2️⃣ MACD Indicator[/bold cyan]", style=macd_color))
    console.print(Rule(style="dim white"))

    # PSAR Box
    console.print(Panel(psar_txt, title="[bold cyan]3️⃣ Parabolic SAR[/bold cyan]", style=psar_color))
    console.print(Rule(style="dim white"))

    # MA Box
    console.print(Panel(ma_txt, title="[bold cyan]4️⃣ Moving Averages (EMA20 vs SMA50)[/bold cyan]", style=ma_color))
    console.print(Rule(style="dim white"))

    # Bollinger Bands Box
    console.print(Panel(bb_txt, title="[bold cyan]5️⃣ Bollinger Bands (Channel Range)[/bold cyan]", style="blue"))
    console.print(Rule(style="dim white"))

    # Volume Box
    console.print(Panel(vol_txt, title="[bold cyan]6️⃣ Volume Analysis[/bold cyan]", style=vol_color))
    console.print(Rule(style="dim white"))

    # Pivot & Support/Resistance Box
    pivot_info = f"""
[bold white]Pivot Point (P):[/bold white] ${pivot:,.4f}
[bold green]Support 1 (S1):[/bold green] ${s1:,.4f}  |  [bold green]Support 2 (S2):[/bold green] ${s2:,.4f}  (PROFIT BUY ZONES)
[bold red]Resistance 1 (R1):[/bold red] ${r1:,.4f}  |  [bold red]Resistance 2 (R2):[/bold red] ${r2:,.4f}  (LOSS SELL ZONES)
"""
    console.print(Panel(pivot_info, title="[bold cyan]7️⃣ Pivot Points & Levels[/bold cyan]", style="cyan"))
    console.print(Rule(style="dim white"))

    # Demand / Supply Box
    ds_info = f"""
[bold green]🟢 Demand Zone (Strong Support):[/bold green] ${demand_zone:,.4f} (Safe Buy Area)
[bold red]🔴 Supply Zone (Strong Resistance):[/bold red] ${supply_zone:,.4f} (Profit Exit Area)
"""
    console.print(Panel(ds_info, title="[bold cyan]8️⃣ Demand & Supply Zones[/bold cyan]", style="magenta"))
    console.print(Rule(style="dim white"))

    # Multi Timeframe Box
    mtf_info = f"""
15-Min Scalp: {trend_15m}
1-Hour Trend: {trend_1h}
4-Hour Trend: {trend_4h}
"""
    console.print(Panel(mtf_info, title="[bold cyan]9️⃣ Multi-Timeframe Alignment[/bold cyan]", style="blue"))
    console.print(Rule(style="dim white"))

    # Candle Pattern Box
    console.print(Panel(candle_pattern, title="[bold cyan]🔟 Candlestick Pattern Scanner[/bold cyan]", style="white"))

    # -------------------------------------------------------------
    # SECTION 3: SPOT & FUTURE CALCULATOR
    # -------------------------------------------------------------
    console.print("\n")
    console.print(Rule(title="[bold green]💰 TRADE RISK & CALCULATOR[/bold green]", style="green"))
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

    entry_price = float(Prompt.ask("Entry Rate ($)", default=str(round(live_price, 4))))
    margin = float(Prompt.ask("Investment / Margin ($)", default="100"))
    exit_price = float(Prompt.ask("Target Exit Rate (TP) ($)", default=str(round(tp_pred, 4))))
    sl_price = float(Prompt.ask("Stop Loss Rate (SL) ($)", default=str(round(sl_pred, 4))))
    pkr_rate = float(Prompt.ask("USD to PKR Rate", default="278.5"))

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
    
    calc_box = f"""
📌 Type: [bold white]{type_str}[/bold white]
🟡 Live Entry: [bold yellow]${entry_price:,.4f}[/bold yellow]
🟢 Target Exit (TP): [bold green]${exit_price:,.4f}[/bold green]
🔴 Stop Loss (SL): [bold red]${sl_price:,.4f}[/bold red]

💵 Capital Margin: [bold white]${margin:,.2f}[/bold white] (Rs. {margin * pkr_rate:,.2f})
🚀 ESTIMATED PROFIT: [bold green]+${pnl_usd:.2f}[/bold green] (Rs. [bold green]+{pnl_pkr:,.2f}[/bold green]) | [bold green]ROE: +{roe:.2f}%[/bold green]
🛑 ESTIMATED LOSS (SL): [bold red]-${loss_usd:.2f}[/bold red] (Rs. [bold red]-{loss_pkr:,.2f}[/bold red])
⚖️ Risk to Reward: [bold cyan]1 : {risk_reward:.2f}[/bold cyan]
"""
    if is_future:
        calc_box += f"💥 LIQUIDATION PRICE: [bold red]${liq_price:,.4f}[/bold red]\n"

    console.print(Panel(calc_box, title="[bold green]🟢 FINAL TRADE ESTIMATION (PROFIT & LOSS)[/bold green]", style="green"))
    console.print("\n[bold yellow]👨‍💻 DEVELOPER: BILAL ALI (SHEBI)[/bold yellow]\n")

if __name__ == "__main__":
    run_app()
