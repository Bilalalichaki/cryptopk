import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "xxxx")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "xxxx")
TELEGRAM_ADMIN_ID  = os.environ.get("TELEGRAM_ADMIN_ID",  "5846593253")

if TELEGRAM_BOT_TOKEN == "xxxx" or TELEGRAM_CHAT_ID == "xxxx":
    raise SystemExit("❌ Render pe TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID set karo!")

PROXIES = None

WATCHLIST = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'LTCUSDT', 'DOTUSDT', 'BCHUSDT',
    'ZECUSDT', 'PEPEUSDT', 'PAXGUSDT', 'ICPUSDT',
]
FUTURES_WATCHLIST = []

COOLDOWN_SECONDS        = 7200
SIGNAL_SCAN_INTERVAL    = 900 #15min
TP_SL_CHECK_INTERVAL    = 30
MIN_AI_SCORE            = 150
GLOBAL_COOLDOWN_SECONDS = 3600
DAILY_SUMMARY_HOUR      = 23

VOLUME_FILTER_ENABLED = True
VOLUME_THRESHOLD      = 0.8

ATR_PERIOD           = 14
SL_ATR_MULTIPLIER    = 1.5
TP1_ATR_MULTIPLIER   = 2.0
TP2_ATR_MULTIPLIER   = 3.5

sent_history            = {}
active_trades           = {}
trade_log               = []
daily_stats             = {
    'date': None,
    'signals': 0,
    'tp1_hits': 0,
    'tp2_hits': 0,
    'sl_hits': 0,
    'pending': 0
}
state_lock              = threading.Lock()
last_global_signal_time = 0
last_daily_summary_date = None



def get_pakistan_time():
    pkt = ZoneInfo('Asia/Karachi')
    return datetime.now(pkt).strftime("%d-%b-%Y | %I:%M %p")


def get_pakistan_date():
    pkt = ZoneInfo('Asia/Karachi')
    return datetime.now(pkt).strftime("%d-%b-%Y")


def get_pakistan_hour():
    pkt = ZoneInfo('Asia/Karachi')
    return datetime.now(pkt).hour

def round_price(p):
    if p >= 1000:     return round(p, 2)
    elif p >= 1:      return round(p, 4)
    elif p >= 0.01:   return round(p, 5)
    elif p >= 0.0001: return round(p, 6)
    else:             return round(p, 8)


def fetch_klines(symbol, timeframe, limit=100, futures=False):
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


def calculate_parabolic_sar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    high = df['high'].values
    low  = df['low'].values
    n    = len(df)
    sar   = [0.0] * n
    trend = [1] * n
    ep    = [0.0] * n
    af    = [af_start] * n
    sar[0]   = low[0]
    ep[0]    = high[0]
    trend[0] = 1
    for i in range(1, n):
        sar[i] = sar[i-1] + af[i-1] * (ep[i-1] - sar[i-1])
        if trend[i-1] == 1:
            if low[i] < sar[i]:
                trend[i] = -1
                sar[i]   = ep[i-1]
                ep[i]    = low[i]
                af[i]    = af_start
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
                sar[i]   = ep[i-1]
                ep[i]    = high[i]
                af[i]    = af_start
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
    df['sar']       = sar
    df['sar_trend'] = trend
    return df


def calculate_atr(df, period=14):
    high_low   = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close  = (df['low']  - df['close'].shift()).abs()
    tr  = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr


def detect_rsi_divergence(df, rsi, lookback=20):
    if len(df) < lookback:
        return "NONE"
    recent     = df.iloc[-lookback:]
    recent_rsi = rsi.iloc[-lookback:]
    price_low_idx  = recent['low'].idxmin()
    price_high_idx = recent['high'].idxmax()
    price_low  = recent.loc[price_low_idx,  'low']
    price_high = recent.loc[price_high_idx, 'high']
    rsi_low    = recent_rsi.loc[price_low_idx]
    rsi_high   = recent_rsi.loc[price_high_idx]
    prev_low_price  = recent['low'].iloc[:lookback//2].min()
    prev_high_price = recent['high'].iloc[:lookback//2].max()
    prev_low_rsi    = recent_rsi.iloc[:lookback//2].min()
    prev_high_rsi   = recent_rsi.iloc[:lookback//2].max()
    if price_low < prev_low_price and rsi_low > prev_low_rsi:
        return "BULLISH"
    if price_high > prev_high_price and rsi_high < prev_high_rsi:
        return "BEARISH"
    return "NONE"


def analyze_tf(df, timeframe_label=""):
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"

    close  = df['close']
    volume = df['volume']

    if VOLUME_FILTER_ENABLED:
        avg_volume     = volume.rolling(20).mean().iloc[-1]
        current_volume = volume.iloc[-1]
        if current_volume < (avg_volume * VOLUME_THRESHOLD):
            return 0, "NEUTRAL"

    delta = close.diff()
    gain  = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss  = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs    = gain / loss
    rsi   = 100 - (100 / (1 + rs))

    ema20 = close.ewm(span=20, adjust=False).mean()
    sma50 = close.rolling(50).mean()

    price      = close.iloc[-1]
    bull, bear = 0, 0

    if rsi.iloc[-1] < 40:    bull += 50
    elif rsi.iloc[-1] < 50:  bull += 30
    elif rsi.iloc[-1] > 60:  bear += 50
    elif rsi.iloc[-1] > 50:  bear += 30

    if price > ema20.iloc[-1] > sma50.iloc[-1]:    bull += 50
    elif price > ema20.iloc[-1]:                    bull += 25
    elif price < ema20.iloc[-1] < sma50.iloc[-1]:  bear += 50
    elif price < ema20.iloc[-1]:                    bear += 25

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram   = macd_line - signal_line

    if macd_line.iloc[-1] > signal_line.iloc[-1] and histogram.iloc[-1] > 0:
        bull += 25
    elif macd_line.iloc[-1] < signal_line.iloc[-1] and histogram.iloc[-1] < 0:
        bear += 25

    sar_df = calculate_parabolic_sar(df)
    if sar_df['sar_trend'].iloc[-1] == 1 and sar_df['sar'].iloc[-1] < price:
        bull += 25
    elif sar_df['sar_trend'].iloc[-1] == -1 and sar_df['sar'].iloc[-1] > price:
        bear += 25

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    if price <= (sma20 - 2*std20).iloc[-1]:
        bull += 25
    elif price >= (sma20 + 2*std20).iloc[-1]:
        bear += 25

    if volume.rolling(5).mean().iloc[-1] > volume.rolling(20).mean().iloc[-1] * 1.2:
        if bull > bear:   bull += 15
        elif bear > bull: bear += 15

    divergence = detect_rsi_divergence(df, rsi)
    if divergence == "BULLISH":
        bull += 20
    elif divergence == "BEARISH":
        bear += 20

    if bull > bear:
        return bull, "LONG"
    elif bear > bull:
        return bear, "SHORT"
    return 0, "NEUTRAL"


def send_telegram_msg(msg, reply_to=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        if res.status_code != 200:
            logger.error(f"[Telegram-Ch] {res.status_code}: {res.text[:200]}")
            return None
        return res.json().get('result', {}).get('message_id')
    except Exception as e:
        logger.error(f"[Telegram-Ch] Exception: {e}")
        return None


def send_admin_msg(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_ADMIN_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        if res.status_code != 200:
            logger.error(f"[Telegram-Admin] {res.status_code}: {res.text[:200]}")
            return None
        return res.json().get('result', {}).get('message_id')
    except Exception as e:
        logger.error(f"[Telegram-Admin] Exception: {e}")
        return None


def reset_daily_stats_if_needed():
    global daily_stats
    today = get_pakistan_date()
    if daily_stats.get('date') != today:
        if daily_stats.get('date') is not None:
            save_day_to_log()
        daily_stats = {
            'date': today,
            'signals': 0,
            'tp1_hits': 0,
            'tp2_hits': 0,
            'sl_hits': 0,
            'pending': 0
        }


def save_day_to_log():
    global daily_stats
    if daily_stats.get('date'):
        trade_log.append(daily_stats.copy())
        logger.info(f"📝 Day saved to log: {daily_stats['date']}")


def get_win_rate(stats=None):
    if stats is None:
        stats = daily_stats
    total_closed = stats['tp1_hits'] + stats['tp2_hits'] + stats['sl_hits']
    if total_closed == 0:
        return 0, 0
    wins = stats['tp1_hits'] + stats['tp2_hits']
    rate = (wins / total_closed) * 100
    return round(rate, 1), total_closed


def build_daily_summary():
    stats = daily_stats
    win_rate, total_closed = get_win_rate(stats)
    if total_closed == 0:     emoji = "😐"
    elif win_rate >= 70:      emoji = "🎉"
    elif win_rate >= 60:      emoji = "✅"
    elif win_rate >= 50:      emoji = "😊"
    else:                     emoji = "⚠️"
    msg = (
        f"📊 *DAILY SUMMARY — {stats['date']}*\n"
        f"═══════════════════════════════\n\n"
        f"📈 *Total Signals:* `{stats['signals']}`\n\n"
        f"✅ *TP1 Hits:* `{stats['tp1_hits']}`\n"
        f"✅ *TP2 Hits:* `{stats['tp2_hits']}`\n"
        f"🛑 *SL Hits:* `{stats['sl_hits']}`\n"
        f"⏳ *Pending:* `{stats['pending']}`\n\n"
        f"═══════════════════════════════\n"
        f"🎯 *Win Rate:* `{win_rate}%` {emoji}\n"
        f"📊 *Closed Trades:* `{total_closed}`\n"
        f"═══════════════════════════════"
    )
    return msg


def check_active_trade_results():
    global daily_stats
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
                daily_stats['tp2_hits'] += 1
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
                daily_stats['tp1_hits'] += 1
            elif recent_low <= trade['sl']:
                send_telegram_msg(
                    f"🛑 *STOP LOSS HIT* 🛑\n\n"
                    f"📌 *Pair:* `{pair}` | *LONG* 🟢\n"
                    f"❌ *SL:* `{trade['sl']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                daily_stats['sl_hits'] += 1
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
                daily_stats['tp2_hits'] += 1
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
                daily_stats['tp1_hits'] += 1
            elif recent_high >= trade['sl']:
                send_telegram_msg(
                    f"🛑 *STOP LOSS HIT* 🛑\n\n"
                    f"📌 *Pair:* `{pair}` | *SHORT* 🔴\n"
                    f"❌ *SL:* `{trade['sl']}`\n\n"
                    f"📅 *Signal Time:* `{sig_time}`\n"
                    f"⏰ *Hit Time:* `{get_pakistan_time()}`",
                    reply_to=sig_msg_id
                )
                daily_stats['sl_hits'] += 1
                remove = True

        if remove:
            with state_lock:
                active_trades.pop(symbol, None)
                if daily_stats['pending'] > 0:
                    daily_stats['pending'] -= 1


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
    if t4h == "NEUTRAL":
        return None
    if t15 != t4h or t1h != t4h:
        return None
    trend = t4h
    score = min(s15, s1h, s4h)
    if score < MIN_AI_SCORE:
        return None
    atr_series = calculate_atr(df_15m, ATR_PERIOD)
    atr        = atr_series.iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None
    price = df_15m['close'].iloc[-1]
    if trend == "LONG":
        badge = "🟢 *BUY / LONG SIGNAL* 🟢"
        sl    = round_price(price - (SL_ATR_MULTIPLIER  * atr))
        tp1   = round_price(price + (TP1_ATR_MULTIPLIER * atr))
        tp2   = round_price(price + (TP2_ATR_MULTIPLIER * atr))
    else:
        badge = "🔴 *SELL / SHORT SIGNAL* 🔴"
        sl    = round_price(price + (SL_ATR_MULTIPLIER  * atr))
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
        f"📈 *SETUP:* 🔥 4h Aligned Trade"
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


def scan_signals():
    global last_global_signal_time, daily_stats
    now = time.time()
    if (now - last_global_signal_time) < GLOBAL_COOLDOWN_SECONDS:
        remaining = int(GLOBAL_COOLDOWN_SECONDS - (now - last_global_signal_time))
        logger.info(f"⏸️ Global cooldown — {remaining}s remaining")
        return
    for symbol in WATCHLIST:
        try:
            res = analyze_and_build_signal(symbol, is_futures=False)
            if res:
                msg, coin, data = res
                if (now - sent_history.get(coin, 0)) > COOLDOWN_SECONDS:
                    msg_id = send_telegram_msg(msg)
                    if msg_id:
                        data['signal_message_id'] = msg_id
                        sent_history[coin]        = now
                        last_global_signal_time   = now
                        with state_lock:
                            active_trades[symbol] = data
                        daily_stats['signals'] += 1
                        daily_stats['pending'] += 1
                        logger.info(f"✅ Signal sent: {coin} (msg_id: {msg_id})")
                        return
        except Exception as e:
            logger.error(f"[Scan] {symbol}: {e}")
    logger.info("❌ No valid signal this scan")


def send_daily_summary():
    summary_msg = build_daily_summary()
    send_admin_msg(summary_msg)
    logger.info("📊 Daily summary sent")


def main_loop():
    global last_daily_summary_date, daily_stats
    logger.info("🚀 Signal Bot Started...")
    logger.info(f"📢 Channel: {TELEGRAM_CHAT_ID}")
    logger.info(f"👤 Admin: {TELEGRAM_ADMIN_ID}")
    last_signal_scan = 0
    while True:
        try:
            now = time.time()
            reset_daily_stats_if_needed()
            check_active_trade_results()
            if (now - last_signal_scan) >= SIGNAL_SCAN_INTERVAL:
                logger.info("🔍 Signal scan starting...")
                scan_signals()
                last_signal_scan = now
                logger.info(f"✅ Scan done. Active: {len(active_trades)}")
            current_date = get_pakistan_date()
            current_hour = get_pakistan_hour()
            if current_hour == DAILY_SUMMARY_HOUR and last_daily_summary_date != current_date:
                send_daily_summary()
                last_daily_summary_date = current_date
            time.sleep(TP_SL_CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"[MainLoop] {e}")
            time.sleep(60)


@app.route('/')
def health():
    return "Bot is running 24/7!", 200


@app.route('/status')
def status():
    win_rate, total_closed = get_win_rate()
    return {
        "status": "alive",
        "active_trades": len(active_trades),
        "today_signals": daily_stats['signals'],
        "today_win_rate": f"{win_rate}%",
        "closed_trades": total_closed,
        "time": get_pakistan_time()
    }, 200


@app.route('/stats')
def stats_route():
    return {
        "today": daily_stats,
        "history": trade_log[-7:],
        "active": len(active_trades)
    }, 200


_scanner_started = False
_scanner_lock    = threading.Lock()


def start_scanner_once():
    global _scanner_started
    with _scanner_lock:
        if not _scanner_started:
            threading.Thread(target=main_loop, daemon=True).start()
            _scanner_started = True
            logger.info("🔧 Scanner thread launched.")


start_scanner_once()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)




# ==========================================
# TEST MESSAGE — ORACLE VM CHECK
# ==========================================
def send_test_on_startup():
    """Bot start hote hi test message bhejta hai."""
    try:
        test_admin = (
            f"🧪 *ORACLE VM TEST*\n\n"
            f"✅ Bot chal raha hai\n"
            f"🖥️ VM: Oracle Cloud\n"
            f"⏰ Time: `{get_pakistan_time()}`"
        )
        send_admin_msg(test_admin)
        
        test_channel = (
            f"🧪 *TEST SIGNAL*\n"
            f"═══════════════════\n"
            f"🪙 *COIN:* TEST\n"
            f"⏰ *TIME:* `{get_pakistan_time()}`\n"
            f"═══════════════════\n\n"
            f"💵 *ENTRY:* `100.00`\n\n"
            f"🎯 *TP 1:* `103.00`\n"
            f"🎯 *TP 2:* `105.00`\n\n"
            f"🛑 *STOP LOSS:* `98.00`\n\n"
            f"═══════════════════\n"
            f"📈 *SETUP:* 🧪 Oracle VM Test"
        )
        send_telegram_msg(test_channel)
        
        logger.info("🧪 Test messages sent")
    except Exception as e:
        logger.error(f"Test failed: {e}")

# Startup pe test bhejo
send_test_on_startup()