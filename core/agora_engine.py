"""
OpenAgora — The Meta Trading Engine
Stocks + Crypto + Prediction Markets | Self-Evolving | Training-Powered

Enhanced with:
- Stock trading via Alpaca API
- Crypto trading via Binance API  
- AI Training Strategy (Q-learning)
- Meta (Facebook) AI integration ready

Usage:
  python core/agora_engine.py --mode simulate
  python core/agora_engine.py --mode live
  python core/agora_engine.py --trade-stock AAPL --buy
  python core/agora_engine.py --trade-crypto BTCUSDT --sell
"""

import os
import sys
import time
import argparse
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.market_feed import MarketFeed
from core.war_chest import log_trade, get_summary
from strategies.meta_strategy import MetaStrategy
from memory.everos_bridge import record_trade, get_strategy_weights, get_top_assets
from reporting.telegram_bot import startup_message, trade_alert, heartbeat, send

SIMULATE = os.getenv("SIMULATE_MODE", "true").lower() == "true"
CYCLE_INTERVAL = 300  # 5 minutes

# Trading class for executing real trades
class TradingExecutor:
    """Execute real trades on stocks and crypto"""
    
    def __init__(self):
        self.feed = MarketFeed()
        self.alpaca_key = os.getenv("ALPACA_API_KEY", "")
        self.alpaca_secret = os.getenv("ALPACA_API_SECRET", "")
        self.binance_key = os.getenv("BINANCE_API_KEY", "")
        self.binance_secret = os.getenv("BINANCE_API_SECRET", "")
        self.is_live = os.getenv("SIMULATE_MODE", "true").lower() != "true"
    
    def execute_stock_order(self, ticker, action, quantity=1):
        """Execute stock order via Alpaca"""
        print(f"[Trading] Stock order: {action} {quantity} {ticker}")
        
        if not self.alpaca_key or not self.alpaca_secret:
            print("[Trading] No Alpaca keys - simulating trade")
            pnl = self._simulate_trade(ticker, action)
            return {"simulated": True, "ticker": ticker, "action": action, "quantity": quantity, "pnl": pnl}
        
        # LIVE execution via Alpaca
        try:
            url = "https://paper-api.alpaca.markets/v2/orders" if self._is_paper() else "https://api.alpaca.markets/v2/orders"
            order = {
                "symbol": ticker,
                "qty": str(quantity),
                "side": action.lower(),
                "type": "market",
                "time_in_force": "day"
            }
            r = requests.post(url, json=order, headers=self._alpaca_headers(), timeout=30)
            if r.status_code in [200, 201]:
                result = r.json()
                print(f"[Trading] LIVE stock order placed: {result.get('id')}")
                return {"simulated": False, "order_id": result.get("id"), "status": result.get("status")}
            else:
                print(f"[Trading] Alpaca error: {r.status_code} {r.text}")
                return {"error": r.text}
        except Exception as e:
            print(f"[Trading] Stock order error: {e}")
            return {"error": str(e)}
    
    def execute_crypto_order(self, symbol, action, quantity=1):
        """Execute crypto order via Binance"""
        print(f"[Trading] Crypto order: {action} {quantity} {symbol}")
        
        if not self.binance_key or not self.binance_secret:
            print("[Trading] No Binance keys - simulating trade")
            pnl = self._simulate_trade(symbol, action)
            return {"simulated": True, "symbol": symbol, "action": action, "quantity": quantity, "pnl": pnl}
        
        # LIVE execution via Binance
        try:
            side = "BUY" if action.upper() == "BUY" else "SELL"
            order = {
                "symbol": symbol,
                "side": side,
                "type": "MARKET",
                "quantity": str(quantity)
            }
            # Note: Binance requires different signing - simplified here
            url = f"{self.feed.binance_base}/order"
            r = requests.post(url, params=order, timeout=30)
            if r.status_code in [200, 201]:
                result = r.json()
                print(f"[Trading] LIVE crypto order placed: {result.get('orderId')}")
                return {"simulated": False, "order_id": result.get("orderId"), "status": "filled"}
            else:
                print(f"[Trading] Binance error: {r.status_code}")
                return {"error": r.text}
        except Exception as e:
            print(f"[Trading] Crypto order error: {e}")
            return {"error": str(e)}
    
    def _is_paper(self):
        """Check if using paper trading"""
        return os.getenv("ALPACA_PAPER", "true").lower() == "true"
    
    def _alpaca_headers(self):
        """Get Alpaca headers"""
        return {
            "APCA-API-KEY-ID": self.alpaca_key,
            "APCA-API-SECRET-KEY": self.alpaca_secret,
            "Content-Type": "application/json"
        }
    
    def _simulate_trade(self, ticker, action):
        """Simulate trade P&L (for testing)"""
        import random
        if action.upper() == "BUY":
            return round(random.uniform(-1, 3), 4)
        return round(random.uniform(-1, 3), 4)
    
    def get_prices(self, asset_type, symbols):
        """Get current prices for assets"""
        if asset_type == "crypto":
            return self.feed.get_crypto_prices(symbols)
        elif asset_type == "stock":
            return self.feed.get_stock_batch(symbols)
        return {}


def print_banner():
    print("""
╔══════════════════════════════════════════════════╗
║          🏛️  O P E N A G O R A  🏛️              ║
║     The Meta Trading Engine — Pantheon v2.0    ║
║   Stocks + Crypto + Predictions | Training    ║
║         AI Q-Learning Self-Evolving             ║
╚══════════════════════════════════════════════════╝
""")


def run_cycle(engine: MetaStrategy, simulate: bool):
    """Execute one full Meta trading cycle"""
    from core.war_chest import get_kill_switch_status, calculate_position_size, get_summary as get_war_summary
    from reporting.telegram_bot import kill_switch_alert
    
    print(f"\n[Agora] {'[SIMULATE]' if simulate else '[LIVE]'} Running Meta cycle...")

    # === CHECK KILL SWITCH ===
    kill_status = get_kill_switch_status()
    if kill_status["triggered"]:
        print(f"[Agora] ⛔ KILL SWITCH TRIGGERED: {kill_status['reason']}")
        kill_switch_alert(kill_status["reason"])
        return None
    
    # Get current position sizing
    war_summary = get_war_summary()
    max_position = calculate_position_size(war_summary["total_pnl"])
    print(f"[Agora] Max position size: ${max_position:.2f}")

    result = engine.run_cycle()
    strategy = result["strategy_selected"]
    signals = result["signals"]

    print(f"[Agora] Strategy selected: {strategy}")
    print(f"[Agora] Signals found: {len(signals)}")

    if not signals:
        print("[Agora] No signals this cycle.")
        return

    # Execute top signal
    top = signals[0]
    asset = top["asset"]
    action = top["action"]
    confidence = top["confidence"]
    asset_type = top["type"]

    # Check confidence threshold (don't fire on low confidence)
    if confidence < 0.5:
        print(f"[Agora] Signal confidence {confidence} too low, skipping")
        return None

    # === LIVE EXECUTION ===
    if not simulate:
        executor = TradingExecutor()
        if asset_type == "stock":
            exec_result = executor.execute_stock_order(asset, action, 1)
        else:
            exec_result = executor.execute_crypto_order(asset, action, 1)
        
        if exec_result.get("simulated", True):
            pnl = 0.0
            print(f"[Agora] Warning: Live mode but order simulated")
        else:
            print(f"[Agora] LIVE order placed: {exec_result.get('order_id')}")
            pnl = 0.0  # Would need to track filled price
    else:
        # === SIMULATE ===
        import random
        if random.random() < confidence:
            pnl = round(random.uniform(0.5, 5.0) * confidence, 4)
        else:
            pnl = round(-random.uniform(0.5, 3.0), 4)

    # Log to War Chest
    total_pnl = log_trade(asset, asset_type, action, 1.0, pnl, strategy)

    # Record to EverOS memory
    record_trade(strategy, asset, pnl)

    # Telegram alert
    trade_alert(asset, action, pnl, total_pnl, strategy, simulate)

    print(f"[Agora] Trade: {action} {asset} | P&L: ${pnl:+.4f} | War Chest: ${total_pnl:+.4f}")

    return pnl


def main():
    parser = argparse.ArgumentParser(description="OpenAgora Meta Trading Engine")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    
    # Stock trading options
    parser.add_argument("--trade-stock", metavar="TICKER", help="Trade a stock (e.g., AAPL)")
    parser.add_argument("--buy", action="store_true", help="Buy action")
    parser.add_argument("--sell", action="store_true", help="Sell action")
    parser.add_argument("--quantity", type=int, default=1, help="Quantity to trade")
    
    # Crypto trading options
    parser.add_argument("--trade-crypto", metavar="SYMBOL", help="Trade crypto (e.g., BTCUSDT)")
    
    # View options
    parser.add_argument("--prices", nargs="+", help="Get prices for assets")
    parser.add_argument("--asset-type", choices=["crypto", "stock"], default="crypto", help="Asset type for --prices")
    
    args = parser.parse_args()

    # Handle one-off commands
    feed = MarketFeed()
    
    # Get prices
    if args.prices:
        prices = feed.get_prices(args.asset_type, args.prices)
        print(f"Prices ({args.asset_type}): {prices}")
        return
    
    # Trade stock
    if args.trade_stock:
        executor = TradingExecutor()
        action = "BUY" if args.buy else "SELL" if args.sell else "HOLD"
        result = executor.execute_stock_order(args.trade_stock, action, args.quantity)
        print(f"Result: {result}")
        return
    
    # Trade crypto
    if args.trade_crypto:
        executor = TradingExecutor()
        action = "BUY" if args.buy else "SELL" if args.sell else "HOLD"
        result = executor.execute_crypto_order(args.trade_crypto, action, args.quantity)
        print(f"Result: {result}")
        return
    
    # Normal trading loop
    from core.war_chest import get_kill_switch_status
    from reporting.telegram_bot import check_commands, crash_alert, kill_command_received
    
    simulate = args.mode == "simulate"

    print_banner()
    print(f"[Agora] Mode: {'SIMULATE 🔵' if simulate else 'LIVE 🔴'}")
    print(f"[Agora] Cycle interval: {CYCLE_INTERVAL}s")

    startup_message(simulate)

    engine = MetaStrategy()
    cycle_count = 0
    remote_kill = False

    while True:
        try:
            # === CHECK REMOTE KILL SWITCH ===
            cmd = check_commands()
            if cmd and cmd.get("command") == "kill":
                remote_kill = True
                kill_command_received()
                print("[Agora] ⛔ Remote kill received, halting...")
                break
            elif cmd and cmd.get("command") == "start":
                remote_kill = False
                print("[Agora] ▶ Remote start received, resuming...")
            
            if remote_kill:
                print("[Agora] ⛔ Remote killed, skipping cycle...")
                time.sleep(CYCLE_INTERVAL)
                continue
            
            run_cycle(engine, simulate)
            cycle_count += 1

            # Heartbeat every 12 cycles (~1 hour)
            if cycle_count % 12 == 0:
                summary = get_summary()
                heartbeat(summary, simulate)
                weights = get_strategy_weights()
                print(f"[Agora] Strategy weights: {weights}")
                top_assets = get_top_assets(3)
                print(f"[Agora] Top assets: {top_assets}")

            if args.once:
                print("[Agora] --once flag set. Exiting.")
                break

            print(f"[Agora] Sleeping {CYCLE_INTERVAL}s...")
            time.sleep(CYCLE_INTERVAL)

        except KeyboardInterrupt:
            print("\n[Agora] Shutdown signal received.")
            summary = get_summary()
            send(
                f"*🏛️ OpenAgora OFFLINE*\n"
                f"Final War Chest: `${summary['total_pnl']:+.4f}`\n"
                f"Total Trades: `{summary['total_trades']}`\n"
                f"_The Agora will return._ 🔱"
            )
            break
        except Exception as e:
            print(f"[Agora] Error: {e}")
            crash_alert(str(e))
            time.sleep(30)


if __name__ == "__main__":
    main()
