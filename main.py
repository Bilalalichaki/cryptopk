import os
import time
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo
import threading
import logging
from flask import Flask
from sklearn.ensemble import RandomForestClassifier
import warnings
warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ================== CONFIG ==================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "xxxx")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "xxxx")
TELEGRAM_ADMIN_ID  = os.environ.get("TELEGRAM_ADMIN_ID",  "xxxx")

if TELEGRAM_BOT_TOKEN == "xxxx" or TELEGRAM_CHAT_ID == "xxxx":
    raise SystemExit("❌ Render pe TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID set karo!")

PROXIES = None
# Render pe persistent disk mount karo (e.g. /data) aur STATE_FILE=/data/bot_state.json set karo
STATE_FILE = os.environ.get("STATE_FILE", "bot_state.json")

WATCHLIST = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
    'ADAUSDT', 'DOGEUSDT', 'LTCUSDT', 'DOTUSDT', 'BCHUSDT',
    'ZECUSDT', 'PEPEUSDT', 'PAXGUSDT', 'ICPUSDT',
]

COOLDOWN_SECONDS        = 7200
SIGNAL_SCAN_INTERVAL    = 900
TP_SL_CHECK_INTERVAL    = 30
MIN_FINAL_SCORE         = 72
GLOBAL_COOLDOWN_SECONDS = 900
DAILY_SUMMARY_HOUR      = 23
TRADE_EXPIRY_HOURS      = 48

VOLUME_FILTER_ENABLED = True
VOLUME_THRESHOLD      = 0.8
VOLUME_FILTER_TFS     = ('15m', '1h')   # 4h/1d pe volume filter nahi

MIN_ALIGNED_TF = 3          # kam az kam itne timeframes ek direction mein

# Risk model: SL distance se TP nikalte hain, taake RR hamesha fixed rahe
ATR_PERIOD    = 14
SL_ATR_MULT   = 1.5
MIN_SL_PCT    = 0.006       # SL kam az kam 0.6% door
TP1_R         = 1.2         # TP1 = 1.2R
TP2_R         = 2.5         # TP2 = 2.5R

AI_MIN_ACCURACY = 0.52      # holdout accuracy is se kam ho to AI ko ignore karo

# ================== STATE ==================
sent_history            = {}
active_trades           = {}
trade_log               = []
daily_stats             = {
    'date': None, 'signals': 0, 'tp1_hits': 0, 'tp2_hits': 0,
    'sl_hits': 0, 'pending': 0, 'trade_details': []
}
state_lock              = threading.RLock()
last_global_signal_time = 0
last_daily_summary_date = None

# ================== HELPERS ==================
def get_pakistan_time():
    return datetime.now(ZoneInfo('Asia/Karachi')).strftime("%d-%b-%Y | %I:%M %p")

def get_pakistan_date():
    return datetime.now(ZoneInfo('Asia/Karachi')).strftime("%d-%b-%Y")

def get_pakistan_hour():
    return datetime.now(ZoneInfo('Asia/Karachi')).hour

def pk_time_from_ms(ms):
    return datetime.fromtimestamp(int(ms) / 1000, ZoneInfo('Asia/Karachi')).strftime("%d-%b-%Y | %I:%M %p")

def round_price(p):
    if p >= 1000:     return round(p, 2)
    elif p >= 1:      return round(p, 4)
    elif p >= 0.01:   return round(p, 5)
    elif p >= 0.0001: return round(p, 6)
    else:             return round(p, 8)

def coin_name(symbol):
    pair = symbol.replace('USDT', '')
    return 'XAU / GOLD' if pair in ('PAXG', 'XAU') else pair

# ================== PERSISTENCE ==================
def save_state():
    try:
        with state_lock:
            data = {
                "sent_history": sent_history,
                "active_trades": active_trades,
                "daily_stats": daily_stats,
                "trade_log": trade_log[-30:],
                "last_global_signal_time": last_global_signal_time,
                "last_daily_summary_date": last_daily_summary_date
            }
            payload = json.dumps(data, default=str)
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w") as f:
            f.write(payload)
        os.replace(tmp, STATE_FILE)   # atomic write
    except Exception as e:
        logger.error(f"Save state error: {e}")

def load_state():
    global sent_history, active_trades, daily_stats, trade_log
    global last_global_signal_time, last_daily_summary_date
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            with state_lock:
                sent_history = data.get("sent_history", {})
                active_trades = data.get("active_trades", {})
                daily_stats = data.get("daily_stats", daily_stats)
                trade_log = data.get("trade_log", [])
                last_global_signal_time = data.get("last_global_signal_time", 0)
                last_daily_summary_date = data.get("last_daily_summary_date", None)
            logger.info(f"✅ State loaded | Active trades: {len(active_trades)}")
    except Exception as e:
        logger.error(f"Load state error: {e}")

# ================== DATA ==================
KLINE_COLS = ['time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
              '_1', '_2', '_3', '_4', '_5']

def _to_df(data):
    df = pd.DataFrame(data, columns=KLINE_COLS)
    for c in ['open', 'high', 'low', 'close', 'volume']:
        df[c] = df[c].astype(float)
    df['time'] = df['time'].astype('int64')
    df['close_time'] = df['close_time'].astype('int64')
    # sirf CLOSED candles rakho (chalti hui candle hata do)
    now_ms = int(time.time() * 1000)
    df = df[df['close_time'] < now_ms].reset_index(drop=True)
    return df

def fetch_klines(symbol, timeframe, limit=100, futures=False):
    try:
        if futures:
            url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        else:
            url = f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}&interval={timeframe}&limit={limit}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
        if isinstance(data, dict) or not data:
            return None
        return _to_df(data)
    except Exception as e:
        logger.error(f"[fetch_klines] {symbol} {timeframe}: {e}")
        return None

def fetch_klines_since(symbol, start_ms, interval='1m'):
    """start_ms ke baad ki closed candles (TP/SL tracking ke liye)"""
    try:
        url = (f"https://data-api.binance.vision/api/v3/klines?symbol={symbol}"
               f"&interval={interval}&startTime={int(start_ms)}&limit=1000")
        res = requests.get(url, proxies=PROXIES, timeout=10)
        data = res.json()
        if isinstance(data, dict):
            return None
        if not data:
            return pd.DataFrame(columns=KLINE_COLS)
        return _to_df(data)
    except Exception as e:
        logger.error(f"[fetch_since] {symbol}: {e}")
        return None

def fetch_live_price(symbol):
    try:
        url = f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url, proxies=PROXIES, timeout=10)
        return float(res.json()['price'])
    except Exception as e:
        logger.error(f"[live_price] {symbol}: {e}")
        return None

def calculate_atr(df, period=14):
    high_low   = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close  = (df['low']  - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def calculate_parabolic_sar(df, af_start=0.02, af_step=0.02, af_max=0.2):
    high = df['high'].values
    low  = df['low'].values
    n    = len(df)
    sar   = [0.0] * n
    trend = [1] * n
    ep    = [0.0] * n
    af    = [af_start] * n
    sar[0] = low[0]
    ep[0]  = high[0]
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
                else:
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
                else:
                    sar[i] = max(sar[i], high[i-1])
    df = df.copy()
    df['sar'] = sar
    df['sar_trend'] = trend
    return df

# ================== AI ==================
AI_FEATURES = ['ema_diff', 'rsi', 'macd_hist', 'vol_ratio', 'returns', 'atr_pct', 'sar_trend']

def build_features(df):
    df = df.copy()
    close = df['close']
    volume = df['volume']

    df['ema20'] = close.ewm(span=20, adjust=False).mean()
    df['ema50'] = close.ewm(span=50, adjust=False).mean()
    df['ema_diff'] = (df['ema20'] - df['ema50']) / close

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi'] = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    df['macd_hist'] = (macd - signal) / close

    df['vol_ratio'] = volume / (volume.rolling(20).mean() + 1e-10)
    df['returns'] = close.pct_change()
    df['atr'] = calculate_atr(df, 14)
    df['atr_pct'] = df['atr'] / close
    df['sar_trend'] = calculate_parabolic_sar(df)['sar_trend']
    return df

def ai_predict_direction(df, horizon=3):
    """
    Returns (confidence, direction). Direction: LONG / SHORT / NEUTRAL.
    - Train sirf un rows pe jinka future result maloom hai (last `horizon` rows nahi)
    - Predict LATEST closed candle pe
    - Holdout accuracy kam ho to model ko unreliable maan ke NEUTRAL (0.5) return
    """
    try:
        if df is None or len(df) < 150:
            return 0.5, "NEUTRAL"

        feat = build_features(df)
        feat['future_return'] = feat['close'].shift(-horizon) / feat['close'] - 1
        feat = feat.dropna(subset=AI_FEATURES)
        if len(feat) < 120:
            return 0.5, "NEUTRAL"

        latest_x = feat[AI_FEATURES].iloc[[-1]].values        # current candle
        labeled = feat.dropna(subset=['future_return'])        # known outcomes only
        X = labeled[AI_FEATURES].values
        y = (labeled['future_return'] > 0).astype(int).values
        if len(X) < 100 or len(np.unique(y)) < 2:
            return 0.5, "NEUTRAL"

        # time-ordered holdout check (purge `horizon` rows beech mein)
        split = int(len(X) * 0.8)
        m_val = RandomForestClassifier(n_estimators=60, max_depth=5, min_samples_leaf=5,
                                       random_state=42, n_jobs=1)
        m_val.fit(X[:split - horizon], y[:split - horizon])
        acc = (m_val.predict(X[split:]) == y[split:]).mean()
        if acc < AI_MIN_ACCURACY:
            return 0.5, "NEUTRAL"

        model = RandomForestClassifier(n_estimators=60, max_depth=5, min_samples_leaf=5,
                                       random_state=42, n_jobs=1)
        model.fit(X, y)
        proba = model.predict_proba(latest_x)[0]
        long_prob = proba[1] if len(proba) > 1 else 0.5

        if long_prob >= 0.60:
            return long_prob, "LONG"
        if long_prob <= 0.40:
            return 1 - long_prob, "SHORT"
        return 0.5, "NEUTRAL"
    except Exception as e:
        logger.error(f"AI error: {e}")
        return 0.5, "NEUTRAL"

# ================== TECHNICAL ANALYSIS ==================
def analyze_tf(df, timeframe_label=""):
    if df is None or len(df) < 50:
        return 0, "NEUTRAL"

    close = df['close']
    volume = df['volume']
    avg_vol = volume.rolling(20).mean().iloc[-1]

    if VOLUME_FILTER_ENABLED and timeframe_label in VOLUME_FILTER_TFS:
        if volume.iloc[-1] < avg_vol * VOLUME_THRESHOLD:
            return 0, "NEUTRAL"

    bull, bear = 0, 0
    price = close.iloc[-1]

    # EMA
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()
    if price > ema20.iloc[-1] > ema50.iloc[-1]:
        bull += 30
    elif price > ema20.iloc[-1]:
        bull += 15
    elif price < ema20.iloc[-1] < ema50.iloc[-1]:
        bear += 30
    elif price < ema20.iloc[-1]:
        bear += 15

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    rsi_val = (100 - (100 / (1 + rs))).iloc[-1]

    if rsi_val < 30:   bull += 25
    elif rsi_val < 45: bull += 12
    elif rsi_val > 70: bear += 25
    elif rsi_val > 55: bear += 12

    # Volume
    if volume.iloc[-1] > avg_vol * 1.3:
        if bull > bear:   bull += 20
        elif bear > bull: bear += 20

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - signal_line
    if hist.iloc[-1] > 0:
        bull += 15
    elif hist.iloc[-1] < 0:
        bear += 15

    # SAR
    sar_df = calculate_parabolic_sar(df)
    if sar_df['sar_trend'].iloc[-1] == 1 and sar_df['sar'].iloc[-1] < price:
        bull += 10
    elif sar_df['sar_trend'].iloc[-1] == -1 and sar_df['sar'].iloc[-1] > price:
        bear += 10

    if bull > bear: return bull, "LONG"
    if bear > bull: return bear, "SHORT"
    return 0, "NEUTRAL"

# ================== TELEGRAM ==================
def send_telegram_msg(msg, reply_to=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg, 'parse_mode': 'Markdown'}
    if reply_to:
        payload['reply_to_message_id'] = reply_to
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        if res.status_code != 200:
            logger.error(f"[Telegram] {res.status_code}: {res.text[:200]}")
            return None
        return res.json().get('result', {}).get('message_id')
    except Exception as e:
        logger.error(f"[Telegram] {e}")
        return None

def send_admin_msg(msg):
    if TELEGRAM_ADMIN_ID == "xxxx":
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TELEGRAM_ADMIN_ID, 'text': msg, 'parse_mode': 'Markdown'}
    try:
        res = requests.post(url, json=payload, proxies=PROXIES, timeout=30)
        return res.json().get('result', {}).get('message_id') if res.status_code == 200 else None
    except Exception:
        return None

# ================== STATS ==================
def reset_daily_stats_if_needed():
    global daily_stats
    today = get_pakistan_date()
    with state_lock:
        if daily_stats.get('date') != today:
            if daily_stats.get('date') is not None:
                trade_log.append(daily_stats.copy())
            daily_stats = {
                'date': today, 'signals': 0, 'tp1_hits': 0, 'tp2_hits': 0,
                'sl_hits': 0, 'pending': len(active_trades), 'trade_details': []
            }
    save_state()

def get_win_rate(stats=None):
    """Win = TP1 tak pohanchne wala trade (TP2 wale bhi TP1 cross karte hain, isliye double count nahi)."""
    if stats is None: stats = daily_stats
    wins = stats['tp1_hits']
    total = wins + stats['sl_hits']
    if total == 0: return 0, 0
    return round(wins / total * 100, 1), total

RESULT_TEXT = {
    'TP2': 'TP2 ✅✅', 'TP1': 'TP1 ✅ (trade chal raha)', 'SL': 'SL ❌',
    'BE': 'TP1 ✅ → Entry pe close ➖', 'EXPIRED': 'Expired ⌛', 'PENDING': 'Pending ⏳'
}

def _trade_block(i, t):
    d_emoji = "🟢" if t.get('direction') == 'LONG' else "🔴"
    res = t.get('result', 'PENDING')
    lines = [
        f"*{i}. {d_emoji} {t.get('coin')}* | {t.get('direction')} | {RESULT_TEXT.get(res, res)}",
        f"   📥 Entry: `{t.get('entry')}`",
        f"   🕒 Entry Time: `{t.get('signal_time', '-')}`",
        f"   🎯 TP1: `{t.get('tp1')}` | TP2: `{t.get('tp2')}` | SL: `{t.get('sl_orig')}`",
    ]
    if t.get('tp1_time'):
        lines.append(f"   ✅ TP1 Hit: `{t['tp1_time']}`")
    if res == 'TP2':
        lines.append(f"   🏆 TP2 Hit: `{t.get('close_time')}`")
    elif res == 'SL':
        lines.append(f"   🛑 SL Hit: `{t.get('close_time')}`")
    elif res == 'BE':
        lines.append(f"   ➖ Entry pe close: `{t.get('close_time')}`")
    elif res == 'EXPIRED':
        lines.append(f"   ⌛ Expire: `{t.get('close_time')}`")
    return "\n".join(lines)

def build_daily_summary():
    with state_lock:
        stats = json.loads(json.dumps(daily_stats))
        trades = list(stats.get('trade_details', []))
        for sym, t in active_trades.items():       # abhi khule trades bhi dikhao
            trades.append({
                'coin': coin_name(sym), 'direction': t['direction'],
                'entry': round_price(t['entry']), 'tp1': t['tp1'], 'tp2': t['tp2'],
                'sl_orig': t.get('sl_orig', t['sl']), 'signal_time': t.get('signal_time'),
                'tp1_time': t.get('tp1_time'),
                'result': 'TP1' if t.get('tp1_hit') else 'PENDING',
            })
    win_rate, total_closed = get_win_rate(stats)
    emoji = "🎉" if win_rate >= 70 else "✅" if win_rate >= 60 else "😊" if win_rate >= 50 else "⚠️" if total_closed > 0 else "😐"

    msg = (
        f"📊 *DAILY SUMMARY — {stats['date']}*\n"
        f"═══════════════════════════════\n\n"
        f"📈 *Total Signals:* `{stats['signals']}`\n\n"
        f"✅ *TP1 Hits:* `{stats['tp1_hits']}` (TP2 included)\n"
        f"🏆 *TP2 Hits:* `{stats['tp2_hits']}`\n"
        f"🛑 *SL Hits:* `{stats['sl_hits']}`\n"
        f"⏳ *Pending:* `{stats['pending']}`\n\n"
        f"═══════════════════════════════\n"
        f"🎯 *Win Rate:* `{win_rate}%` {emoji}\n"
        f"📊 *Closed Trades:* `{total_closed}`\n"
        f"═══════════════════════════════\n"
    )
    if trades:
        msg += "\n📋 *TRADE DETAILS:*\n\n"
        msg += "\n\n".join(_trade_block(i, t) for i, t in enumerate(trades, 1))
    return msg

def split_message(text, limit=3800):
    """Telegram 4096 chars se lambi message nahi leta, isliye trade blocks ke beech se todo."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if len(cur) + len(block) + 2 > limit and cur:
            parts.append(cur)
            cur = block
        else:
            cur = f"{cur}\n\n{block}" if cur else block
    if cur:
        parts.append(cur)
    return parts

# ================== TRADE TRACKING ==================
def _hit_msg(kind, trade, pair, price, hit_time=None):
    hit_time = hit_time or get_pakistan_time()
    side = "*LONG* 🟢" if trade['direction'] == 'LONG' else "*SHORT* 🔴"
    head = f"📌 *Pair:* `{pair}` | {side}\n💰 *Entry:* `{trade['entry']}`\n"
    foot = f"\n\n📅 *Signal Time:* `{trade.get('signal_time', 'N/A')}`"
    if kind != 'TP1' and trade.get('tp1_time'):
        foot += f"\n✅ *TP1 Time:* `{trade['tp1_time']}`"
    foot += f"\n⏰ *Hit Time:* `{hit_time}`"
    if kind == 'TP1':
        return ("✅ *SUCCESSFUL HIT — TARGET 1* ✅\n\n🎯 *TRADE IN PROFIT!*\n\n" + head +
                f"✅ *TP1:* `{price}`\n\n💡 *SL ab entry pe move ho gaya — risk-free trade!*" + foot)
    if kind == 'TP2':
        return ("✅ *SUCCESSFUL HIT — TARGET 2 (FULL TP)* ✅\n\n🔥🔥🔥 *PERFECT TRADE!* 🔥🔥🔥\n\n" + head +
                f"✅ *TP2:* `{price}`" + foot)
    if kind == 'SL':
        return ("🛑 *STOP LOSS HIT* 🛑\n\n" + head + f"❌ *SL:* `{price}`" + foot)
    if kind == 'BE':
        return ("➖ *CLOSED AT ENTRY (BREAKEVEN)* ➖\n\nTP1 hit ho chuka tha, baaki position entry pe close.\n\n" + head + foot)
    return ("⌛ *SIGNAL EXPIRED* ⌛\n\nTarget/SL nahi laga, trade expire.\n\n" + head + foot)

def _is_long(trade):
    return trade['direction'] == 'LONG'

def process_trade_candles(symbol, trade, df, outbox):
    """
    Closed 1m candles ko time order mein process karta hai.
    Ek hi candle mein SL aur TP dono touch hon to SL pehle maana jata hai (conservative).
    Hit time candle ke asli time se aata hai. Returns True agar trade close ho gaya.
    """
    pair = coin_name(symbol)
    is_long = _is_long(trade)
    reply = trade.get('signal_message_id')
    trade.setdefault('sl_orig', trade['sl'])

    def finish(kind, price, hit_time):
        trade['close_time'] = hit_time
        outbox.append((_hit_msg(kind, trade, pair, price, hit_time), reply))
        if kind == 'SL':
            daily_stats['sl_hits'] += 1
        if kind == 'TP2':
            daily_stats['tp2_hits'] += 1
        daily_stats['trade_details'].append({
            'coin': pair, 'direction': trade['direction'],
            'entry': round_price(trade['entry']),
            'tp1': trade['tp1'], 'tp2': trade['tp2'], 'sl_orig': trade['sl_orig'],
            'signal_time': trade.get('signal_time'),
            'tp1_time': trade.get('tp1_time'),
            'close_time': hit_time,
            'exit_price': price, 'result': kind,
        })
        sent_history[pair] = time.time()
        if daily_stats['pending'] > 0:
            daily_stats['pending'] -= 1

    for _, c in df.iterrows():
        hi, lo = c['high'], c['low']
        ht = pk_time_from_ms(c['time'])
        sl_hit  = (lo <= trade['sl'])  if is_long else (hi >= trade['sl'])
        tp1_hit = (hi >= trade['tp1']) if is_long else (lo <= trade['tp1'])
        tp2_hit = (hi >= trade['tp2']) if is_long else (lo <= trade['tp2'])

        if not trade['tp1_hit']:
            if sl_hit:
                finish('SL', trade['sl'], ht)
                return True
            if tp1_hit:
                trade['tp1_hit'] = True
                trade['tp1_time'] = ht
                trade['sl'] = round_price(trade['entry'])     # breakeven
                daily_stats['tp1_hits'] += 1
                outbox.append((_hit_msg('TP1', trade, pair, trade['tp1'], ht), reply))
                if tp2_hit:
                    trade['tp2_hit'] = True
                    finish('TP2', trade['tp2'], ht)
                    return True
        else:
            if sl_hit:
                finish('BE', trade['entry'], ht)
                return True
            if tp2_hit:
                trade['tp2_hit'] = True
                finish('TP2', trade['tp2'], ht)
                return True

    # expiry
    age_h = (time.time() * 1000 - trade['signal_ts_ms']) / 3600000
    if age_h > TRADE_EXPIRY_HOURS:
        finish('EXPIRED', None, get_pakistan_time())
        return True
    return False

def check_active_trade_results():
    with state_lock:
        symbols = list(active_trades.keys())

    for symbol in symbols:
        with state_lock:
            trade = active_trades.get(symbol)
            if not trade:
                continue
            start = trade.get('last_checked_ms') or trade['signal_ts_ms']
            start = int(start)

        df = fetch_klines_since(symbol, start)      # network lock ke bahar
        if df is None:
            continue

        outbox = []
        closed = False
        with state_lock:
            trade = active_trades.get(symbol)
            if not trade:
                continue
            if not df.empty:
                closed = process_trade_candles(symbol, trade, df, outbox)
                trade['last_checked_ms'] = int(df['time'].iloc[-1]) + 60000
            else:
                closed = process_trade_candles(symbol, trade, df, outbox)  # sirf expiry check
            if closed:
                active_trades.pop(symbol, None)

        for msg, reply in outbox:
            send_telegram_msg(msg, reply_to=reply)
        save_state()

# ================== SIGNAL ENGINE ==================
def analyze_and_build_signal(symbol, is_futures=False):
    df_15m = fetch_klines(symbol, '15m', limit=500, futures=is_futures)
    df_1h  = fetch_klines(symbol, '1h',  limit=100, futures=is_futures)
    df_4h  = fetch_klines(symbol, '4h',  limit=100, futures=is_futures)
    df_1d  = fetch_klines(symbol, '1d',  limit=100, futures=is_futures)

    if any(x is None for x in [df_15m, df_1h, df_4h, df_1d]):
        return None

    s15, t15 = analyze_tf(df_15m, '15m')
    s1h, t1h = analyze_tf(df_1h,  '1h')
    s4h, t4h = analyze_tf(df_4h,  '4h')
    s1d, t1d = analyze_tf(df_1d,  '1d')

    logger.info(f"🔍 {symbol} | 15m:{s15}/{t15} | 1h:{s1h}/{t1h} | 4h:{s4h}/{t4h} | 1d:{s1d}/{t1d}")

    tfs = [(s15, t15), (s1h, t1h), (s4h, t4h), (s1d, t1d)]
    trends = [t for _, t in tfs]
    long_count  = trends.count("LONG")
    short_count = trends.count("SHORT")

    if long_count >= MIN_ALIGNED_TF and short_count == 0:
        trend, count = "LONG", long_count
    elif short_count >= MIN_ALIGNED_TF and long_count == 0:
        trend, count = "SHORT", short_count
    else:
        return None   # mixed / opposite TF wale setups skip

    scores = [s for s, t in tfs if t == trend]
    tech_score = min(scores) + (20 if count == 4 else 10)
    setup_label = "🏆 4-TF Aligned (MAX)" if count == 4 else "🔥 3-TF Aligned"

    # AI check
    ai_prob, ai_dir = ai_predict_direction(df_15m)
    if ai_dir != "NEUTRAL" and ai_dir != trend:
        logger.info(f"❌ {symbol} AI disagreed ({ai_dir} vs {trend}) — skipped")
        return None

    final_score = (tech_score * 0.70) + (ai_prob * 100 * 0.30)
    if final_score < MIN_FINAL_SCORE:
        return None

    # Entry = live price, risk = ATR-based with floor, TPs = R multiples
    price = fetch_live_price(symbol) or df_15m['close'].iloc[-1]
    atr = calculate_atr(df_1h, ATR_PERIOD).iloc[-1]
    if pd.isna(atr) or atr <= 0:
        return None

    risk = max(SL_ATR_MULT * atr, price * MIN_SL_PCT)
    if trend == "LONG":
        badge = "🟢 *BUY / LONG SIGNAL* 🟢"
        sl  = round_price(price - risk)
        tp1 = round_price(price + risk * TP1_R)
        tp2 = round_price(price + risk * TP2_R)
    else:
        badge = "🔴 *SELL / SHORT SIGNAL* 🔴"
        sl  = round_price(price + risk)
        tp1 = round_price(price - risk * TP1_R)
        tp2 = round_price(price - risk * TP2_R)

    pair = coin_name(symbol)

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
        f"📈 *SETUP:* {setup_label}"
    )

    now_ms = int(time.time() * 1000)
    return msg, pair, {
        'direction': trend,
        'entry': price,
        'sl': sl,
        'sl_orig': sl,
        'tp1': tp1,
        'tp2': tp2,
        'tp1_hit': False,
        'tp2_hit': False,
        'signal_time': get_pakistan_time(),
        'signal_ts_ms': now_ms,
        'last_checked_ms': (now_ms // 60000 + 1) * 60000,   # agli poori 1m candle se check shuru
        'score': round(final_score, 1),
    }

def scan_signals():
    global last_global_signal_time
    now = time.time()
    if (now - last_global_signal_time) < GLOBAL_COOLDOWN_SECONDS:
        logger.info(f"⏸️ Global cooldown — {int(GLOBAL_COOLDOWN_SECONDS - (now - last_global_signal_time))}s left")
        return

    candidates = []
    for symbol in WATCHLIST:
        try:
            coin = coin_name(symbol)
            with state_lock:
                if symbol in active_trades:
                    continue
                if (now - sent_history.get(coin, 0)) <= COOLDOWN_SECONDS:
                    continue
            res = analyze_and_build_signal(symbol)
            if res:
                candidates.append((symbol,) + res)
        except Exception as e:
            logger.error(f"[Scan] {symbol}: {e}")

    if not candidates:
        logger.info("❌ No valid signal this scan")
        return

    # sabse high score wala signal bhejo
    symbol, msg, coin, data = max(candidates, key=lambda c: c[3]['score'])
    msg_id = send_telegram_msg(msg)
    if msg_id:
        data['signal_message_id'] = msg_id
        with state_lock:
            sent_history[coin] = now
            last_global_signal_time = now
            active_trades[symbol] = data
            daily_stats['signals'] += 1
            daily_stats['pending'] += 1
        save_state()
        logger.info(f"✅ Signal sent: {coin} (score {data['score']}, {len(candidates)} candidates)")

def send_daily_summary():
    for part in split_message(build_daily_summary()):
        send_admin_msg(part)
        time.sleep(1)
    logger.info("📊 Daily summary sent")

# ================== MAIN ==================
def main_loop():
    global last_daily_summary_date
    logger.info("🚀 Bot v2 Started")
    last_signal_scan = 0

    while True:
        try:
            reset_daily_stats_if_needed()
            check_active_trade_results()

            if (time.time() - last_signal_scan) >= SIGNAL_SCAN_INTERVAL:
                logger.info("🔍 Scanning...")
                last_signal_scan = time.time()
                scan_signals()

            if get_pakistan_hour() == DAILY_SUMMARY_HOUR and last_daily_summary_date != get_pakistan_date():
                send_daily_summary()
                last_daily_summary_date = get_pakistan_date()
                save_state()

            time.sleep(TP_SL_CHECK_INTERVAL)
        except Exception as e:
            logger.error(f"[MainLoop] {e}")
            time.sleep(60)

@app.route('/')
def health():
    return "Bot is running 24/7!", 200

@app.route('/status')
def status():
    with state_lock:
        win_rate, total = get_win_rate()
        return {
            "status": "alive",
            "active_trades": len(active_trades),
            "today_signals": daily_stats['signals'],
            "win_rate": f"{win_rate}%",
            "closed": total,
            "time": get_pakistan_time()
        }, 200

_scanner_started = False
_scanner_lock = threading.Lock()

def start_scanner_once():
    global _scanner_started
    with _scanner_lock:
        if not _scanner_started:
            load_state()
            threading.Thread(target=main_loop, daemon=True).start()
            _scanner_started = True

start_scanner_once()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
