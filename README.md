# Crypto & Gold Trading Signal Bot 🚀

An automated, high-precision trading signal engine built in Python, designed to run 24/7 on cloud infrastructure. It continuously analyzes high-volume cryptocurrency assets and Gold, generating real-time technical trade signals with live TP/SL tracking delivered directly to Telegram.

---

## 🌟 Key Features

* **24/7 Cloud Ready:** Integrated with a background Flask web server for seamless continuous hosting on Render.
* **Multi-Asset Coverage:** Scans top high-volume crypto assets (BTC, ETH, SOL, etc.) alongside Spot & Futures Gold (PAXG / XAU).
* **Multi-Timeframe Analysis:** Combines **15m Scalp** and **1h Intraday** technical indicators for reliable entries.
* **Smart Indicator Confluence:** Evaluates setups using RSI (14), EMA (20), and SMA (50) to filter out false breakouts.
* **Live TP / SL Alerts:** Tracks active trades dynamically and dispatches instant Telegram updates when Target 1, Target 2, or Stop Loss prices are reached.
* **Anti-Spam Cooldown:** Configured with an intelligent cooldown period per asset to prevent signal spamming.
* **Clean Telegram Alerts:** Styled with bold formatting and monospace code blocks for quick entry/exit copying.

---

## 🛠️ Tech Stack

* **Language:** Python 3.x
* **Core Libraries:** `requests`, `pandas`, `pytz`, `Flask`
* **API Source:** Binance Public Market Data API
* **Alert System:** Telegram Bot API
* **Deployment:** Render Cloud Platform

---

## ⚙️ Configuration & Logic

* **Time Zone:** Asia/Karachi (PKT)
* **Cooldown Interval:** 3 Hours per coin
* **Scoring Threshold:** Configurable AI Score filter for high-probability setups
# cryptopk