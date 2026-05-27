"""
OpenAgora — Meta Strategy
The self-adjusting brain. Weights shift based on EverOS memory.
This is what makes OpenAgora Meta.
Enhanced with AI Training Strategy integration.
"""

import os
import json
from memory.everos_bridge import get_strategy_weights, add_lesson
from core.market_feed import MarketFeed
from strategies.training_strategy import get_training_strategy, record_training_outcome, get_training_stats
import random


class MetaStrategy:
    """
    Meta-recursive strategy selector.
    Uses EverOS memory to dynamically weight sub-strategies.
    Capital flows toward what's winning. Always evolving.
    Now includes AI Training Strategy for self-improvement.
    """

    def __init__(self):
        self.feed = MarketFeed()
        self.strategies = ["momentum", "arbitrage", "mean_reversion", "trend_follow", "training"]
        self.training = get_training_strategy()

    def select_strategy(self):
        """Pick strategy based on historical win-rate weights"""
        weights = get_strategy_weights()
        if not weights:
            return random.choice(self.strategies)
        available = {k: v for k, v in weights.items() if k in self.strategies}
        if not available:
            return random.choice(self.strategies)
        total = sum(available.values())
        r = random.uniform(0, total)
        cumulative = 0
        for strategy, weight in available.items():
            cumulative += weight
            if r <= cumulative:
                return strategy
        return self.strategies[0]

    def analyze_crypto(self, prices: dict):
        """Analyze crypto prices for signals — threshold: 2% move"""
        signals = []
        for coin, data in prices.items():
            change = data.get("usd_24h_change", 0)
            price = data.get("usd", 0)
            if change and abs(change) > 0.5:  # lowered from 5% to 2%
                direction = "BUY" if change > 0 else "SELL"
                confidence = min(abs(change) / 5, 1.0)  # scaled to new threshold
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
        training_analysis = self.training.analyze_with_ai(snapshot.get("crypto", {}), "crypto")
        training_signals = training_analysis.get("signals", [])

        all_signals = crypto_signals + pred_signals + training_signals
        all_signals.sort(key=lambda x: x["confidence"], reverse=True)

        if all_signals:
            top = all_signals[0]
            add_lesson(f"Top signal: {top['asset']} ({top['action']}) confidence={top['confidence']} via {strategy}")
            if strategy == "training":
                state = training_analysis.get("state", "neutral")
                action = training_analysis.get("action", "HOLD")
                self._pending_training = {"state": state, "action": action}

        return {
            "strategy_selected": strategy,
            "signals": all_signals[:5],
            "training_state": training_analysis.get("state", "unknown"),
            "training_action": training_analysis.get("action", "none"),
            "training_stats": get_training_stats(),
            "timestamp": snapshot["timestamp"]
        }

    def record_trade_result(self, pnl):
        """Record trade result for training learning"""
        if hasattr(self, "_pending_training") and self._pending_training:
            record_training_outcome(
                self._pending_training["state"],
                self._pending_training["action"],
                pnl
            )
            self.training.decay_epsilon()
            self._pending_training = None
