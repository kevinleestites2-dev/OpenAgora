"""
QuantMind → Pantheon Bridge
===========================
Wires quant-mind's knowledge retrieval into OpenAgora's reflect() cycle
and TraderZero's signal advisor layer.

Architecture:
  QuantMind Knowledge Base (papers, news, factors)
       ↓ semantic query
  QuantMindAdvisor.query(topic, context)
       ↓ returns research_signal dict
  OpenAgora everos_bridge.py reflect()  →  uses research_signal in Fable 5 prompt
  TraderZero signal_advisor.py          →  pre-trade research context

Usage (standalone test):
  python quantmind_prime_bridge.py --query "mean reversion crypto bear market"

Author: ZapiaPrime × Forgemaster | 2026-06-10
"""

import os
import json
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("QuantMindBridge")
logging.basicConfig(level=logging.INFO, format="[QuantMind] %(message)s")

# ── Config ────────────────────────────────────────────────────────────────────
OR_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
OR_MODEL = os.environ.get("OPENROUTER_MODEL",   "anthropic/claude-fable-5")

ARXIV_BASE   = "https://export.arxiv.org/search/?searchtype=all&query={query}&max_results=5&sortBy=submittedDate&sortOrder=descending"
CRYPTONEWS   = "https://cryptonews.com/news/feed/"  # fallback RSS

# ── QuantMind Advisor ─────────────────────────────────────────────────────────

_ADVISOR_SYSTEM = """You are QuantMind, a quantitative finance research intelligence layer.

You receive:
1. A semantic query describing a trading regime, strategy, or market condition
2. Abstracts from recent academic papers (arXiv quant-fin)
3. Optional current market context

Your output is a structured research signal:
- regime_assessment: current market regime inferred from research (trending/mean-reverting/volatile/unclear)
- strategy_bias: directional bias implied by research (bullish/bearish/neutral/avoid)
- key_factors: list of 3-5 quantitative factors most relevant right now
- risk_flags: list of research-backed risk warnings
- confidence: low/medium/high — how much the research supports a clear signal
- synthesis: 2-3 sentence plain English summary of what the research says to do

Be precise. If papers are inconclusive, say so. No filler. This feeds a live trading engine."""

class QuantMindAdvisor:
    """Semantic research intelligence for Pantheon trading Primes."""

    def __init__(self):
        self.cache: dict = {}
        self.cache_ttl = 3600  # 1 hour

    def _fetch_arxiv(self, query: str) -> list[dict]:
        """Pull recent quant-fin papers from arXiv."""
        try:
            encoded = urllib.parse.quote(f"quantitative finance {query}")
            url = ARXIV_BASE.format(query=encoded)
            req = urllib.request.Request(url, headers={"User-Agent": "QuantMindPrime/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                raw = r.read().decode("utf-8", errors="ignore")

            # Parse atom XML minimally
            papers = []
            entries = raw.split("<entry>")[1:]
            for entry in entries[:5]:
                title_start = entry.find("<title>") + 7
                title_end   = entry.find("</title>")
                title       = entry[title_start:title_end].strip()

                abs_start   = entry.find("<summary>") + 9
                abs_end     = entry.find("</summary>")
                abstract    = entry[abs_start:abs_end].strip()[:600]

                id_start    = entry.find("<id>") + 4
                id_end      = entry.find("</id>")
                arxiv_id    = entry[id_start:id_end].strip()

                if title and abstract:
                    papers.append({"title": title, "abstract": abstract, "url": arxiv_id})

            logger.info(f"Fetched {len(papers)} papers for: {query}")
            return papers
        except Exception as e:
            logger.warning(f"arXiv fetch failed: {e}")
            return []

    def _call_fable5(self, query: str, papers: list[dict], market_context: str = "") -> dict:
        """Run Fable 5 synthesis over retrieved papers."""
        papers_block = "\n\n".join(
            f"[{i+1}] {p['title']}\n{p['abstract']}"
            for i, p in enumerate(papers)
        ) if papers else "No papers retrieved — rely on general quant research knowledge."

        context_block = f"\nCurrent market context: {market_context}" if market_context else ""

        user_msg = f"""Query: {query}{context_block}

Recent Research:
{papers_block}

Produce the research signal JSON."""

        payload = json.dumps({
            "model": OR_MODEL,
            "messages": [
                {"role": "system", "content": _ADVISOR_SYSTEM},
                {"role": "user",   "content": user_msg}
            ],
            "max_tokens": 600,
            "response_format": {"type": "json_object"}
        }).encode()

        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {OR_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/kevinleestites2-dev",
                "X-Title": "QuantMind-PantheonBridge"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            result = json.loads(r.read())
            raw = result["choices"][0]["message"]["content"].strip()
            # Parse JSON from response
            try:
                signal = json.loads(raw)
            except json.JSONDecodeError:
                # Extract JSON block if wrapped in markdown
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                signal = json.loads(raw[start:end]) if start >= 0 else {"synthesis": raw}
            return signal

    def query(self, topic: str, market_context: str = "", force_refresh: bool = False) -> dict:
        """
        Main entry point for Pantheon Primes.

        Args:
            topic:          e.g. "crypto mean reversion", "momentum breakdown bear market"
            market_context: e.g. "BTC -8% last 24h, funding rate negative, vol spike"
            force_refresh:  bypass cache

        Returns:
            research_signal dict with keys:
              regime_assessment, strategy_bias, key_factors,
              risk_flags, confidence, synthesis
        """
        cache_key = f"{topic}:{market_context}"
        now = datetime.now(timezone.utc).timestamp()

        if not force_refresh and cache_key in self.cache:
            cached_at, signal = self.cache[cache_key]
            if now - cached_at < self.cache_ttl:
                logger.info(f"Cache hit for: {topic}")
                return signal

        papers  = self._fetch_arxiv(topic)
        signal  = self._call_fable5(topic, papers, market_context)
        signal["_papers_used"] = len(papers)
        signal["_queried_at"]  = datetime.now(timezone.utc).isoformat()
        signal["_topic"]       = topic

        self.cache[cache_key] = (now, signal)
        logger.info(f"Signal generated | bias={signal.get('strategy_bias','?')} conf={signal.get('confidence','?')}")
        return signal

    def format_for_reflect(self, signal: dict) -> str:
        """Format signal as a compact string for injection into OpenAgora reflect() prompt."""
        return (
            f"[QuantMind Research Signal]\n"
            f"Regime: {signal.get('regime_assessment','unknown')}\n"
            f"Bias: {signal.get('strategy_bias','neutral')}\n"
            f"Confidence: {signal.get('confidence','low')}\n"
            f"Key Factors: {', '.join(signal.get('key_factors', []))}\n"
            f"Risk Flags: {', '.join(signal.get('risk_flags', []))}\n"
            f"Synthesis: {signal.get('synthesis','')}"
        )


# ── Singleton for import ──────────────────────────────────────────────────────
_advisor = QuantMindAdvisor()

def get_research_signal(topic: str, market_context: str = "") -> str:
    """One-liner for OpenAgora/TraderZero to call. Returns formatted string."""
    try:
        signal = _advisor.query(topic, market_context)
        return _advisor.format_for_reflect(signal)
    except Exception as e:
        logger.error(f"QuantMind bridge error: {e}")
        return "[QuantMind] Unavailable — no research signal this cycle."


# ── CLI test ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", default="crypto momentum mean reversion")
    parser.add_argument("--context", default="")
    args = parser.parse_args()

    print("\n" + "="*60)
    print(get_research_signal(args.query, args.context))
    print("="*60)
