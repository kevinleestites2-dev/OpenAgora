# OpenAgora 🏛️
### The Meta Trading Engine — Stocks + Crypto + Prediction Markets

> *The Agora was the beating heart of ancient civilization — commerce, ideas, and power in one place. OpenAgora is that for the Pantheon.*

**Built by:** The Forgemaster | **Version:** v2.0 Enhanced

---

## What It Is

OpenAgora is a **self-evolving, Meta-recursive trading bot** that operates across:
- 📈 **Stocks** — via Marketstack API + Alpaca (real trading ready)
- ₿ **Crypto** — via CoinGecko + Binance (real trading ready)
- 🎯 **Prediction Markets** — via Polymarket + Kalshi

It doesn't just trade. It **watches itself trade**, learns from every win and loss via EverOS memory, and evolves its own strategy weights over time.

**Now with AI Training Strategy (Q-Learning):**
- Uses reinforcement learning to improve decisions
- Learns from historical market data
- Self-adjusts based on outcomes
- Saves Q-table for persistence

---

## Architecture

```
OpenAgora v2.0
├── core/
│   ├── agora_engine.py       # Main orchestrator — Meta brain
│   ├── market_feed.py        # Unified data feed (stocks + crypto + predictions + training)
│   └── war_chest.py          # MidasPrime integration — logs all P&L
├── strategies/
│   ├── meta_strategy.py      # Meta layer — self-adjusting weights + training integration
│   └── training_strategy.py  # AI Q-learning strategy (NEW!)
├── memory/
│   ├── everos_bridge.py      # EverOS long-term memory integration
│   └── trade_log.json        # Persistent trade history
├── reporting/
│   └── telegram_bot.py       # Pantheon Deploy Rule — all vitals to Telegram
├── logs/
│   └── war_chest.json        # MidasPrime War Chest sync
│   └── q_table.json         # Training Q-table (NEW!)
├── .env.example              # All required keys
├── requirements.txt
└── README.md
```

---

## The Meta Layer + AI Training

OpenAgora is **self-aware**. After every trade cycle:
1. It logs the result to EverOS memory
2. It recalculates strategy win rates
3. It shifts capital weight toward winning strategies
4. **NEW:** It uses Q-learning to train and improve decisions
5. It broadcasts vitals to Telegram

This is not a static bot. It evolves.

### AI Training Strategy
- Uses **Q-learning** (reinforcement learning)
- Tracks states: strong_bull, bull, neutral, bear, strong_bear
- Actions: BUY, SELL, HOLD (with exploration)
- Learns from actual trade outcomes
- Persists Q-table to disk

---

## Quick Start

```bash
git clone https://github.com/kevinleestites2-dev/OpenAgora
cd OpenAgora
pip install -r requirements.txt
cp .env.example .env
# Fill in your keys
python core/agora_engine.py --mode simulate
```

## One-Click Commands

```bash
# Get crypto prices
python core/agora_engine.py --prices bitcoin ethereum solana --asset-type crypto

# Get stock prices  
python core/agora_engine.py --prices AAPL GOOGL MSFT --asset-type stock

# Trade a stock (simulated)
python core/agora_engine.py --trade-stock AAPL --buy --quantity 10

# Trade crypto (simulated)
python core/agora_engine.py --trade-crypto BTCUSDT --buy --quantity 1

# Run one training cycle
python core/agora_engine.py --once
```

## Environment Variables

```bash
# Required for stock trading
ALPACA_API_KEY=your_alpaca_key
ALPACA_API_SECRET=your_alpaca_secret

# Required for crypto trading
BINANCE_API_KEY=your_binance_key  
BINANCE_API_SECRET=your_binance_secret

# Required for market data
MARKETSTACK_API_KEY=your_marketstack_key

# Telegram notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## Revenue Flow

All profits auto-sync to MidasPrime's War Chest:
- `logs/war_chest.json` — real-time P&L
- Telegram broadcasts every trade result
- ZapiaPrime can query status on demand

---

## Pantheon Role

| Layer | Component |
|-------|-----------|
| Data | OpenStock + CoinGecko + Polymarket + Kalshi |
| Memory | EverOS (long-term trade memory) |
| Training | Q-Learning Strategy |
| Trading | Alpaca (stocks) + Binance (crypto) |
| Reporting | Telegram (ZeusPrime bot token) |
| Treasury | MidasPrime War Chest |

---

*"The Agora never closes."* 🏛️🔱