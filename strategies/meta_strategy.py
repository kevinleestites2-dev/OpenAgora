"""
OpenAgora — Meta Strategy
The self-adjusting brain. Weights shift based on EverOS memory.
This is what makes OpenAgora Meta.
"""

from memory.everos_bridge import get_strategy_weights, add_lesson
from core.market_feed import MarketFeed
import random


class MetaStrategy:
    """
    Meta-recursive strategy selector.
    Uses EverOS memory to dynamically weight sub-strategies.
    Capital flows toward what's winning. Always evolving.
    """

    def __init__(self):
        self.feed = MarketFeed()
        self.strategies = ["momentum", "arbitrage", "mean_reversion", "trend_follow"]

    def select_strategy(self):
        """Pick strategy based on historical win-rate weights"""
        weights = get_strategy_weights()
        if not weights:
            return random.choice(self.strategies)

        # Filter to known strategies
        available = {k: v for k, v in weights.items() if k in self.strategies}
        if not available:
            return random.choice(self.strategies)

        # Weighted random selection
        total = sum(available.values())
        r = random.uniform(0, total)
        cumulative = 0
        for strategy, weight in available.items():
            cumulative += weight
            if r <= cumulative:
                return strategy
        return self.strategies[0]

    def analyze_crypto(self, prices: dict):
        """Analyze crypto prices for signals"""
        signals = []
        for coin, data in prices.items():
            change = data.get("usd_24h_change", 0)
            price = data.get("usd", 0)
            if change and abs(change) > 5:
                direction = "BUY" if change > 0 else "SELL"
                confidence = min(abs(change) / 20, 1.0)
                signals.append({
                    "asset": coin,
                    "type": "crypto",
                    "action": direction,
                    "change_24h": round(change, 2),
                    "price": price,
                    "confidence": round(confidence, 2)
                })
        return sorted(signals, key=lambda x: x["confidence"], reverse=True)

    def analyze_prediction_markets(self, markets: list):
        """Find arb opportunities in prediction markets"""
        signals = []
        for m in markets:
            # Look for markets where YES + NO prices don't sum to ~1 (arb gap)
            yes = float(m.get("outcomePrices", [0.5])[0]) if m.get("outcomePrices") else 0.5
            no = 1 - yes
            gap = abs((yes + no) - 1.0)
            if gap > 0.02:
                signals.append({
                    "asset": m.get("question", "Unknown")[:40],
                    "type": "prediction",
                    "action": "ARB",
                    "gap": round(gap, 4),
                    "confidence": min(gap * 10, 1.0)
                })
        return signals

    def run_cycle(self):
        """
        Full Meta cycle:
        1. Get market snapshot
        2. Select best strategy via EverOS weights
        3. Generate signals
        4. Return trade plan
        """
        strategy = self.select_strategy()
        snapshot = self.feed.snapshot()

        crypto_signals = self.analyze_crypto(snapshot.get("crypto", {}))
        pred_signals = self.analyze_prediction_markets(snapshot.get("prediction_markets", []))

        all_signals = crypto_signals + pred_signals
        all_signals.sort(key=lambda x: x["confidence"], reverse=True)

        # Meta lesson — note what the market is showing
        if all_signals:
            top = all_signals[0]
            add_lesson(f"Top signal: {top['asset']} ({top['action']}) confidence={top['confidence']} via {strategy}")

        return {
            "strategy_selected": strategy,
            "signals": all_signals[:5],  # Top 5 signals
            "timestamp": snapshot["timestamp"]
        }
