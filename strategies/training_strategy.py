"""
OpenAgora — Training Strategy
AI-powered strategy training with reinforcement learning concepts.
Uses historical data to learn and improve trading decisions.
"""

import os
import json
import random
from datetime import datetime
from collections import defaultdict


class TrainingStrategy:
    """
    Training Strategy with AI-powered learning.
    Analyzes historical data, learns from outcomes, and improves decisions.
    """
    
    def __init__(self):
        self.name = "training"
        self.q_table = defaultdict(lambda: defaultdict(float))
        self.gamma = 0.9  # Discount factor
        self.alpha = 0.1   # Learning rate
        self.epsilon = 0.1  # Exploration rate
        
        # Track training history
        self.history = []
        self.wins = 0
        self.losses = 0
        
        # Load Q-table if exists
        self._load_q_table()
    
    def _get_state(self, prices, asset_type="crypto"):
        """Discretize price data into state"""
        if not prices:
            return "neutral"
        
        if asset_type == "crypto":
            # Use price changes
            changes = []
            for coin, data in prices.items():
                change = data.get("usd_24h_change", 0)
                if change:
                    changes.append(change)
            
            if not changes:
                return "neutral"
            
            avg_change = sum(changes) / len(changes)
            
            if avg_change > 5:
                return "strong_bull"
            elif avg_change > 2:
                return "bull"
            elif avg_change < -5:
                return "strong_bear"
            elif avg_change < -2:
                return "bear"
            return "neutral"
        
        return "neutral"
    
    def _get_action(self, state):
        """Epsilon-greedy action selection"""
        if random.random() < self.epsilon:
            return random.choice(["BUY", "SELL", "HOLD"])
        
        # Exploit best known action
        q_values = self.q_table[state]
        if not q_values:
            return random.choice(["BUY", "SELL", "HOLD"])
        
        return max(q_values.keys(), key=lambda a: q_values[a])
    
    def _update_q_table(self, state, action, reward, next_state):
        """Q-learning update rule"""
        old_q = self.q_table[state][action]
        
        # Max Q-value for next state
        next_q_values = self.q_table[next_state]
        max_next_q = max(next_q_values.values()) if next_q_values else 0
        
        # Bellman equation
        new_q = old_q + self.alpha * (reward + self.gamma * max_next_q - old_q)
        self.q_table[state][action] = new_q
    
    def analyze_with_ai(self, prices, asset_type="crypto"):
        """Use Q-learning to analyze and generate signals"""
        state = self._get_state(prices, asset_type)
        action = self._get_action(state)
        
        signals = []
        
        if asset_type == "crypto":
            for coin, data in prices.items():
                change = data.get("usd_24h_change", 0)
                price = data.get("usd", 0)
                
                if action == "BUY" and change > 0:
                    confidence = min(abs(change) / 15, 1.0)
                    signals.append({
                        "asset": coin,
                        "type": "crypto",
                        "action": "BUY",
                        "change_24h": round(change, 2),
                        "price": price,
                        "confidence": round(confidence, 2)
                    })
                elif action == "SELL" and change < 0:
                    confidence = min(abs(change) / 15, 1.0)
                    signals.append({
                        "asset": coin,
                        "type": "crypto",
                        "action": "SELL",
                        "change_24h": round(change, 2),
                        "price": price,
                        "confidence": round(confidence, 2)
                    })
        
        # Sort by confidence
        signals.sort(key=lambda x: x["confidence"], reverse=True)
        
        return {
            "state": state,
            "action": action,
            "signals": signals[:5]
        }
    
    def record_outcome(self, state, action, pnl):
        """Record trade outcome and update Q-table"""
        # Assign reward based on P&L
        if pnl > 0:
            reward = 1.0
            self.wins += 1
        elif pnl < 0:
            reward = -1.0
            self.losses += 1
        else:
            reward = 0.0
        
        # Determine next state (simplified - use current as next)
        next_state = state  # Simplified
        
        # Update Q-table
        self._update_q_table(state, action, reward, next_state)
        
        # Record in history
        self.history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "state": state,
            "action": action,
            "pnl": pnl,
            "reward": reward
        })
        
        # Save periodically
        if len(self.history) % 10 == 0:
            self._save_q_table()
    
    def get_win_rate(self):
        """Get current win rate"""
        total = self.wins + self.losses
        if total == 0:
            return 0.5
        return self.wins / total
    
    def decay_epsilon(self):
        """Reduce exploration over time"""
        self.epsilon = max(0.01, self.epsilon * 0.99)
    
    def _save_q_table(self):
        """Save Q-table to file"""
        path = os.path.join(os.path.dirname(__file__), "..", "logs", "q_table.json")
        try:
            # Convert defaultdict to regular dict for JSON serialization
            data = {k: dict(v) for k, v in self.q_table.items()}
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Training] Save error: {e}")
    
    def _load_q_table(self):
        """Load Q-table from file"""
        path = os.path.join(os.path.dirname(__file__), "..", "logs", "q_table.json")
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                    self.q_table = defaultdict(lambda: defaultdict(float), data)
        except Exception as e:
            print(f"[Training] Load error: {e}")
    
    def get_strategy_stats(self):
        """Get strategy performance stats"""
        return {
            "name": self.name,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.get_win_rate(), 3),
            "epsilon": round(self.epsilon, 3),
            "total_trades": len(self.history)
        }


# Singleton instance for global use
_training_strategy = None

def get_training_strategy():
    """Get global training strategy instance"""
    global _training_strategy
    if _training_strategy is None:
        _training_strategy = TrainingStrategy()
    return _training_strategy


def analyze_with_training(prices, asset_type="crypto"):
    """Convenience function for training analysis"""
    return get_training_strategy().analyze_with_ai(prices, asset_type)


def record_training_outcome(state, action, pnl):
    """Convenience function to record outcome"""
    get_training_strategy().record_outcome(state, action, pnl)


def get_training_stats():
    """Get training strategy stats"""
    return get_training_strategy().get_strategy_stats()