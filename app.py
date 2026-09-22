import streamlit as st
import requests
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# Page Config
st.set_page_config(page_title="Crypto Live Dashboard", layout="wide")

# Har 5 Second Me Auto Refresh
st_autorefresh(interval=5000, key="datarefresh")

st.title("🚀 CRYPTO & GOLD LIVE PRO DASHBOARD")
st.caption("👨‍💻 Developer: Bilal Ali (Shebi)")

# Top Bar Symbol Selection / Multi Watchlist
coin = st.sidebar.selectbox("Select Coin", ["BTC", "ETH", "PAXG", "ZEC", "SOL", "BNB"], index=0)

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
        df['volume'] = df['volume'].astype(float)
        return df
    except Exception:
        return None

df_1h = get_binance_klines(coin, interval="1h")

if df_1h is not None and not df_1h.empty:
    live_price = df_1h['close'].iloc[-1]
    
    # RSI
    delta = df_1h['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = (100 - (100 / (1 + rs))).iloc[-1]

    # Predictions Calculation
    tp_pred = live_price * 1.025
    sl_pred = live_price * 0.985

    # LIVE PREDICTION CARDS (COLOR CODED)
    st.markdown("### 🎯 Live Predictions & Signals")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.warning(f"🟡 SAFE ENTRY\n\n### ${live_price:,.4f}")
    with col2:
        st.success(f"🟢 TAKE PROFIT (TP)\n\n### ${tp_pred:,.4f}")
    with col3:
        st.error(f"🔴 STOP LOSS (SL)\n\n### ${sl_pred:,.4f}")

    st.divider()

    # INDICATORS LIVE STATUS
    st.markdown("### 📊 Live Technical Indicators")
    ind_col1, ind_col2, ind_col3 = st.columns(3)

    with ind_col1:
        st.info(f"**RSI (14)**: {rsi:.2f}")
    with ind_col2:
        ema20 = df_1h['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        st.info(f"**EMA 20**: ${ema20:,.2f}")
    with ind_col3:
        vol = df_1h['volume'].iloc[-1]
        st.info(f"**Live Volume**: {vol:,.2f}")

else:
    st.error("Live Data Fetch Nahi Ho Saka!")
