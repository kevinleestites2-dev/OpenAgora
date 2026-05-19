# OpenAgora 🏛️
### The Meta Trading Engine — Stocks + Crypto + Prediction Markets

> *The Agora was the beating heart of ancient civilization — commerce, ideas, and power in one place. OpenAgora is that for the Pantheon.*

**Built by:** The Forgemaster | **Pantheon Role:** MidasPrime Revenue Engine v2

---

## What It Is

OpenAgora is a **self-evolving, Meta-recursive trading bot** that operates across:
- 📈 **Stocks** — via OpenStock + Marketstack API
- ₿ **Crypto** — via CoinGecko (free, no key) + Binance
- 🎯 **Prediction Markets** — via Polymarket + Kalshi (ZeusPrime logic absorbed)

It doesn't just trade. It **watches itself trade**, learns from every win and loss via EverOS memory, and evolves its own strategy weights over time.

---

## Architecture

```
OpenAgora
├── core/
│   ├── agora_engine.py       # Main orchestrator — Meta brain
│   ├── market_feed.py        # Unified data feed (stocks + crypto + predictions)
│   └── war_chest.py          # MidasPrime integration — logs all P&L
├── strategies/
│   ├── base_strategy.py      # Abstract strategy class
│   ├── momentum.py           # Momentum / trend following
│   ├── arbitrage.py          # Cross-market arb (Poly vs Kalshi)
│   └── meta_strategy.py      # Meta layer — self-adjusting weights
├── memory/
│   ├── everos_bridge.py      # EverOS long-term memory integration
│   └── trade_log.json        # Persistent trade history
├── reporting/
│   └── telegram_bot.py       # Pantheon Deploy Rule — all vitals to Telegram
├── logs/
│   └── war_chest.json        # MidasPrime War Chest sync
├── .env.example              # All required keys
├── requirements.txt
└── README.md
```

---

## The Meta Layer

OpenAgora is **self-aware**. After every trade cycle:
1. It logs the result to EverOS memory
2. It recalculates strategy win rates
3. It shifts capital weight toward winning strategies
4. It broadcasts vitals to Telegram

This is not a static bot. It evolves.

---

## Revenue Flow

All profits auto-sync to MidasPrime's War Chest:
- `logs/war_chest.json` — real-time P&L
- Telegram broadcasts every trade result
- ZapiaPrime can query status on demand

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

---

## Pantheon Role

| Layer | Component |
|-------|-----------|
| Data | OpenStock + CoinGecko + Polymarket + Kalshi |
| Memory | EverOS (long-term trade memory) |
| Reporting | Telegram (ZeusPrime bot token) |
| Treasury | MidasPrime War Chest |
| Oversight | ZapiaPrime (The Conduit) |

---

*"The Agora never closes."* 🏛️🔱
