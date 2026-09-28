import os
import time
import requests
import pandas as pd
from datetime import datetime
import pytz
import threading
import logging
from flask import Flask

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "xxxx")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "xxxx")

if TELEGRAM_BOT_TOKEN == "xxxx" or TELEGRAM_CHAT_ID == "xxxx":
    raise SystemExit("❌ Render pe TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID set karo!")

PROXIES = None

WATCHLIST = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT', 'LINKUSDT', 'SUIUSDT',
    'NEARUSDT', 'APTUSDT', 'LTCUSDT', 'DOTUSDT', 'BCHUSDT',
    'ZECUSDT', 'PEPEUSDT', 'SHIBUSDT', 'FETUSDT',
    'RENDERUSDT', 'INJUSDT', 'TIAUSDT', 'TAOUSDT', 'SEIUSDT',
    'PAXGUSDT', 'ICPUSDT',
]
FUTURES_WATCHLIST = []

# ---- TIMING ----
COOLDOWN_SECONDS     = 7200      # 2 hours per coin
SIGNAL_SCAN_INTERVAL = 600       # 10 min
TP_SL_CHECK_INTERVAL = 30        # 30 sec
MIN_AI_SCORE         = 150       # Higher threshold (kam signals, zyada accurate)

# ---- FILTERS ----
VOLUME_FILTER_ENABLED = True
VOLUME_THRESHOLD      = 0.8

# ---- ATR SETTINGS ----
ATR_PERIOD           = 14
SL_ATR_MULTIPLIER    = 1.5       # SL = 1.5 × ATR
TP1_ATR_MULTIPLIER   = 2.0       # TP1 = 2.0 × ATR
TP2_ATR_MULTIPLIER   = 3.5       # TP2 = 3.5 × ATR

# ---- GLOBAL COOLDOWN (kam signals) ----
GLOBAL_COOLDOWN_SECONDS = 3600   # 1 hour between ANY signal

sent_history     = {}
active_trades    = {}
state_lock       = threading.Lock()
last_global_signal_time = 0


def get_pakistan_time():
    pkt = pytz.timezone('Asia/Karachi')
    return datetime.now(pkt).strftime("%d-%b-%Y | %I:%M %p")


def round_price(p):
    if p >= 1000:     return round(p, 2)
    elif p >= 1:      return round(p, 4)
    elif p >= 0.01:   return round(p, 5)
    elif p >= 0.0001: return round(p, 6)
    else:             return round(p, 8)


def fetch_klines(symbol, timeframe, limit=200, futures=False):
    try:
        if futures:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        else:
            url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"

        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()

        if isinstance(data, dict) or not data:
            logger.warning(f"[fetch_klines] Bad response {symbol}: {str(data)[:150]}")
            return None

        df = pd.DataFrame(data, columns=[
            'time', 'open', 'high', 'low', 'close', 'volume',
            '_1', '_2', '_3', '_4', '_5', '_6'
        ])
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = df[c].astype(float)
        return df
    except Exception as e:
        logger.error(f"[fetch_klines] {symbol} {timeframe}: {e}")
        return None


# ==========================================
# PARABOLIC SAR
# ==========================================
def calculate_parabolic_sar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    high = df['high'].values
    low  = df['low'].values
    n = len(df)

    sar = [0.0] * n
    trend = [1] * n
    ep = [0.0] * n
    af = [af_start] * n

    sar[0] = low[0]
    ep[0] = high[0]
    trend[0] = 1

    for i in range(1, n):
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])

        if trend[i-1] == 1:
            if low[i] < sar[i]:
                trend[i] = -1
                sar[i] = ep[i-1]
                ep[i] = low[i]
                af[i] = af_start
            else:
                trend[i] = 1
                if high[i] > ep[i-1]:
                    ep[i] = high[i]
                    af[i] = min(af[i-1] + af_step, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
                if i >= 2:
                    sar[i] = min(sar[i], low[i-1], low[i-2])
                elif i >= 1:
                    sar[i] = min(sar[i], low[i-1])
        else:
            if high[i] > sar[i]:
                trend[i] = 1
                sar[i] = ep[i-1]
                ep[i] = high[i]
                af[i] = af_start
            else:
                trend[i] = -1
                if low[i] < ep[i-1]:
                    ep[i] = low[i]
                    af[i] = min(af[i-1] + af_step, af_max)
                else:
                    ep[i] = ep[i-1]
                    af[i] = af[i-1]
                if i >= 2:
                    sar[i] = max(sar[i], high[i-1], high[i-2])
                elif i >= 1:
                    sar[i] = max(sar[i], high[i-1])

    df = df.copy()
    df['sar'] = sar
    df['sar_trend'] = trend
    return df


# ==========================================
# ATR CALCULATION
# ==========================================
def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


# ==========================================
# RSI DIVERGENCE DETECTION
# ==========================================
def detect_rsi_divergence(df, rsi, lookback=20):
    """
    Bullish Divergence: Price Lower Low + RSI Higher Low
    Bearish Divergence: Price Higher High + RSI Lower High
    """
    if len(df) < lookback:
        return "NONE"

    recent = df.iloc[-lookback:]
    recent_rsi = rsi.iloc[-lookback:]

    # Find lows and highs
    price_low_idx  = recent['low'].idxmin()
    price_high_idx = recent['high'].idxmax()

    price_low  = recent.loc[price_low_idx, 'low']
    price_high = recent.loc[price_high_idx, 'high']
    rsi_low    = recent_rsi.loc[price_low_idx]
    rsi_high   = recent_rsi.loc[price_high_idx]

    # Compare with previous extreme
    prev_low_price = recent['low'].iloc[:lookback//2].min()
    prev_high_price = recent['high'].iloc[:lookback//2].max()
    prev_low_rsi = recent_rsi.iloc[:lookback//2].min()
    prev_high_rsi = recent_rsi.iloc[:lookback//2].max()

    # Bullish: price lower low, RSI higher low
    if price_low < prev_low_price and rsi_low > prev_low_rsi:
        return "BULLISH"

    # Bearish: price higher high, RSI lower high
    if price_high > prev_high_price and rsi_high < prev_high_rsi:
        return "BEARISH"

    return "NONE"


# ==========================================
# TECHNICAL ANALYSIS — Full Indicators
# ==========================================
def analyze_tf(df, timeframe_label=""):
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"

    close  = df['close']
    volume = df['volume']

    # ---- VOLUME FILTER ----
    if VOLUME_FILTER_ENABLED:
        avg_volume = volume.rolling(20).mean().iloc[-1]
        current_volume = volume.iloc[-1]
        if current_volume < (avg_volume * VOLUME_THRESHOLD):
            return 0, "NEUTRAL"

    # ---- RSI ----
    delta = close.diff()
    gain  = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))

    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()

    price = close.iloc[-1]
    bull, bear = 0, 0

    # ---- RSI SCORE (max 50) ----
    if rsi.iloc[-1] < 40:    bull += 50
    elif rsi.iloc[-1] < 50:  bull += 30
    elif rsi.iloc[-1] > 60:  bear += 50
    elif rsi.iloc[-1] > 50:  bear += 30

    # ---- EMA20 + SMA50 SCORE (max 50) ----
    if price > ema20.iloc[-1] > sma50.iloc[-1]:    bull += 50
    elif price > ema20.iloc[-1]:                    bull += 25
    elif price < ema20.iloc[-1] < sma50.iloc[-1]:  bear += 50
    elif price < ema20.iloc[-1]:                    bear += 25

    # ---- MACD SCORE (max 25) ----
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram   = macd_line - signal_line

    macd_val   = macd_line.iloc[-1]
    signal_val = signal_line.iloc[-1]
    hist_val   = histogram.iloc[-1]

    if macd_val > signal_val and hist_val > 0:
        bull += 25
    elif macd_val < signal_val and hist_val < 0:
        bear += 25

    # ---- PARABOLIC SAR SCORE (max 25) ----
    sar_df = calculate_parabolic_sar(df)
    sar_value = sar_df['sar'].iloc[-1]
    sar_trend = sar_df['sar_trend'].iloc[-1]

    if sar_trend == 1 and sar_value < price:
        bull += 25
    elif sar_trend == -1 and sar_value > price:
        bear += 25

    # ---- BOLLINGER BANDS SCORE (max 25) ----
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper_band = sma20 + (2 * std20)
    lower_band = sma20 - (2 * std20)

    if price <= lower_band.iloc[-1]:
        bull += 25   # Oversold — LONG
    elif price >= upper_band.iloc[-1]:
        bear += 25   # Overbought — SHORT

    # ---- VOLUME TREND SCORE (max 15) ----
    vol_avg_5  = volume.rolling(5).mean().iloc[-1]
    vol_avg_20 = volume.rolling(20).mean().iloc[-1]

    if vol_avg_5 > vol_avg_20 * 1.2:
        # Volume badh raha hai — current trend confirm
        if bull > bear:  bull += 15
        elif bear > bull: bear += 15

    # ---- RSI DIVERGENCE SCORE (max 20) ----
    divergence = detect_rsi_divergence(df, rsi)
    if divergence == "BULLISH":
        bull += 20
    elif divergence == "BEARISH":
        bear += 20

    if bull > bear:   return bull, "LONG"
    elif bear > bull: return bear, "SHORT"
    return 0, "NEUTRAL"


def send_telegram_msg(msg, reply_to=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': msg,
        'parse_mode': 'Markdown'
    }
    if reply_to:
        payload['reply_to_message_id'] = reply_to

    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        if res.status_code != 200:
            logger.error(f"[Telegram] {res.status_code}: {res.text[:200]}")
            return None
        return res.json().get('result', {}).get('message_id')
    except Exception as e:
        logger.error(f"[Telegram] Exception: {e}")
        return None


def check_active_trade_results():
    with state_lock:
        symbols = list(active_trades.keys())

    for symbol in symbols:
        trade = active_trades.get(symbol)
        if trade is None:
            continue

        is_futures = symbol in FUTURES_WATCHLIST
        df = fetch_klines(symbol, '1m', limit=5, futures=is_futures)
        if df is None:
            continue

        recent_high = df['high'].iloc[-3:].max()
        recent_low  = df['low'].iloc[-3:].min()

        pair = symbol.replace('USDT', '')
        if pair in ['PAXG', 'XAU']:
            pair = 'XAU / GOLD'

        d = trade['direction']
        remove = False

        sig_time   = trade.get('signal_time', 'N/A')
        sig_msg_id = trade.get('signal_message_id')

        if d == 'LONG':
            if recent_high >= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(
                    f"✅ *SUCCESSFUL HIT — TARGET 2 (FULL TP)* ✅\n\n"
                    f"🔥🔥🔥 *PERFECT TRADE!* 🔥🔥🔥\n\n"
                    f"📌 *Pair:* `{pair}` | *LONG* 🟢\n"
                    f"💰 *Entry:* `{trade['entry']}`\n"
                    f"✅ *TP2:* `{trade['tp2']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                trade['tp2_hit'] = True
                remove = True

            elif recent_high >= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(
                    f"✅ *SUCCESSFUL HIT — TARGET 1* ✅\n\n"
                    f"🎯 *TRADE IN PROFIT!*\n\n"
                    f"📌 *Pair:* `{pair}` | *LONG* 🟢\n"
                    f"💰 *Entry:* `{trade['entry']}`\n"
                    f"✅ *TP1:* `{trade['tp1']}`\n\n"
                    f"💡 *Move SL to entry — risk-free trade now!*\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                trade['tp1_hit'] = True

            elif recent_low <= trade['sl']:
                send_telegram_msg(
                    f"🛑 *STOP LOSS HIT* 🛑\n\n"
                    f"📌 *Pair:* `{pair}` | *LONG* 🟢\n"
                    f"❌ *SL:* `{trade['sl']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                remove = True

        elif d == 'SHORT':
            if recent_low <= trade['tp2'] and not trade['tp2_hit']:
                send_telegram_msg(
                    f"✅ *SUCCESSFUL HIT — TARGET 2 (FULL TP)* ✅\n\n"
                    f"🔥🔥🔥 *PERFECT TRADE!* 🔥🔥🔥\n\n"
                    f"📌 *Pair:* `{pair}` | *SHORT* 🔴\n"
                    f"💰 *Entry:* `{trade['entry']}`\n"
                    f"✅ *TP2:* `{trade['tp2']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                trade['tp2_hit'] = True
                remove = True

            elif recent_low <= trade['tp1'] and not trade['tp1_hit']:
                send_telegram_msg(
                    f"✅ *SUCCESSFUL HIT — TARGET 1* ✅\n\n"
                    f"🎯 *TRADE IN PROFIT!*\n\n"
                    f"📌 *Pair:* `{pair}` | *SHORT* 🔴\n"
                    f"💰 *Entry:* `{trade['entry']}`\n"
                    f"✅ *TP1:* `{trade['tp1']}`\n\n"
                    f"💡 *Move SL to entry — risk-free trade now!*\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                trade['tp1_hit'] = True

            elif recent_high >= trade['sl']:
                send_telegram_msg(
                    f"🛑 *STOP LOSS HIT* 🛑\n\n"
                    f"📌 *Pair:* `{pair}` | *SHORT* 🔴\n"
                    f"❌ *SL:* `{trade['sl']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                remove = True

        if remove:
            with state_lock:
                active_trades.pop(symbol, None)


# ==========================================
# SIGNAL BUILDER — With 4h Confirmation
# ==========================================
def analyze_and_build_signal(symbol, is_futures=False):
    df_15m = fetch_klines(symbol, '15m', futures=is_futures)
    df_1h  = fetch_klines(symbol, '1h',  futures=is_futures)
    df_4h  = fetch_klines(symbol, '4h',  limit=100, futures=is_futures)

    if df_15m is None or df_1h is None or df_4h is None:
        return None

    s15, t15 = analyze_tf(df_15m, "15m")
    s1h, t1h = analyze_tf(df_1h,  "1h")
    s4h, t4h = analyze_tf(df_4h,  "4h")

    logger.info(f"🔍 {symbol} | 15m: {s15}/{t15} | 1h: {s1h}/{t1h} | 4h: {s4h}/{t4h}")

    # ---- 4h CONFIRMATION (ZAROORI) ----
    if t4h == "NEUTRAL":
        return None

    # Dono 15m aur 1h ka trend 4h ke saath match hona chahiye
    if t15 != t4h or t1h != t4h:
        return None   # 4h ke against signals skip

    # ---- FINAL TREND ----
    trend = t4h
    # Score = sab ka minimum (sabse kamzor link)
    score = min(s15, s1h, s4h)

    if score < MIN_AI_SCORE:
        return None

    label = "🔥 4h Aligned Trade"

    # ---- ATR-BASED SL/TP ----
    atr_series = calculate_atr(df_15m, ATR_PERIOD)
    atr = atr_series.iloc[-1]

    if pd.isna(atr) or atr <= 0:
        return None

    price = df_15m['close'].iloc[-1]

    if trend == "LONG":
        badge = "🟢 *BUY / LONG SIGNAL* 🟢"
        sl    = round_price(price - (SL_ATR_MULTIPLIER * atr))
        tp1   = round_price(price + (TP1_ATR_MULTIPLIER * atr))
        tp2   = round_price(price + (TP2_ATR_MULTIPLIER * atr))
    else:
        badge = "🔴 *SELL / SHORT SIGNAL* 🔴"
        sl    = round_price(price + (SL_ATR_MULTIPLIER * atr))
        tp1   = round_price(price - (TP1_ATR_MULTIPLIER * atr))
        tp2   = round_price(price - (TP2_ATR_MULTIPLIER * atr))

    pair = symbol.replace('USDT', '')
    if pair in ['PAXG', 'XAU']:
        pair = 'XAU / GOLD'

    msg = (
        f"{badge}\n"
        f"═══════════════════\n"
        f"🪙 *COIN:* `{pair}`\n"
        f"⏰ *TIME:* `{get_pakistan_time()}`\n"
        f"═══════════════════\n\n"
        f"💵 *ENTRY:* `{round_price(price)}`\n\n"
        f"🎯 *TP 1:* `{tp1}`\n"
        f"🎯 *TP 2:* `{tp2}`\n\n"
        f"🛑 *STOP LOSS:* `{sl}`\n\n"
        f"═══════════════════\n"
        f"📈 *SETUP:* {label}"
    )

    return msg, pair, {
        'direction': trend,
        'entry': price,
        'sl': sl,
        'tp1': tp1,
        'tp2': tp2,
        'tp1_hit': False,
        'tp2_hit': False,
        'signal_time': get_pakistan_time()
    }


# ==========================================
# SCAN SIGNALS — With Global Cooldown
# ==========================================
def scan_signals():
    global last_global_signal_time

    now = time.time()

    # Global cooldown check
    if (now - last_global_signal_time) < GLOBAL_COOLDOWN_SECONDS:
        remaining = int(GLOBAL_COOLDOWN_SECONDS - (now - last_global_signal_time))
        logger.info(f"⏸️ Global cooldown — {remaining}s remaining")
        return

    # Best signal dhundho (highest score)
    best_signal = None
    best_score = 0

    for symbol in WATCHLIST:
        try:
            res = analyze_and_build_signal(symbol, is_futures=False)
            if res:
                msg, coin, data = res
                # Cooldown check
                if (now - sent_history.get(coin, 0)) > COOLDOWN_SECONDS:
                    # Score calculate karo (dobara)
                    # Yahan hum simple approach le rahe hain — pehla best signal
                    if best_signal is None:
                        best_signal = (msg, coin, data, symbol)
        except Exception as e:
            logger.error(f"[Scan] {symbol}: {e}")

    # Sirf 1 signal per scan (best)
    if best_signal:
        msg, coin, data, symbol = best_signal
        msg_id = send_telegram_msg(msg)
        if msg_id:
            data['signal_message_id'] = msg_id
            sent_history[coin] = now
            last_global_signal_time = now   # Global cooldown start
            with state_lock:
                active_trades[symbol] = data
            logger.info(f"✅ Signal sent: {coin} (msg_id: {msg_id})")
            logger.info(f"⏸️ Global cooldown started: {GLOBAL_COOLDOWN_SECONDS}s")
    else:
        logger.info("❌ No valid signal this scan")


def main_loop():
    logger.info("🚀 Signal Bot Started...")
    logger.info(f"⏱️ Signal scan: {SIGNAL_SCAN_INTERVAL}s | TP/SL check: {TP_SL_CHECK_INTERVAL}s")
    logger.info(f"📊 Volume filter: {'ON' if VOLUME_FILTER_ENABLED else 'OFF'}")
    logger.info(f"🧠 Indicators: RSI + EMA20 + SMA50 + MACD + SAR + Bollinger + Volume Trend + RSI Divergence")
    logger.info(f"📈 Timeframes: 15m + 1h + 4h (all must align)")
    logger.info(f"🎯 Min Score: {MIN_AI_SCORE}")
    logger.info(f"⏸️ Global Cooldown: {GLOBAL_COOLDOWN_SECONDS}s ({GLOBAL_COOLDOWN_SECONDS//60} min)")
    logger.info(f"💰 ATR-based SL/TP (dynamic)")

    last_s