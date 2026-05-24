"""
Sentiment Analyst Agent — News sentiment scoring.

Analyzes recent news from yfinance and generates a weighted sentiment signal.
Uses keyword-based sentiment classification (no paid NLP API needed).
"""

import logging
import re
from typing import Dict, Any, List

from agents.models import AnalystSignal

logger = logging.getLogger(__name__)

# Sentiment keywords for Indian market context
POSITIVE_KEYWORDS = [
    "upgrade", "outperform", "buy", "bullish", "profit", "growth", "beat",
    "record", "surge", "rally", "breakout", "expansion", "dividend",
    "acquisition", "partnership", "approval", "contract", "order win",
    "strong results", "exceeds", "surprise", "upside", "momentum",
    "new high", "block deal", "stake increase", "FII buying",
]

NEGATIVE_KEYWORDS = [
    "downgrade", "underperform", "sell", "bearish", "loss", "decline",
    "miss", "weak", "crash", "fall", "breakdown", "contraction",
    "debt", "default", "fraud", "probe", "investigation", "penalty",
    "resignation", "layoff", "shutdown", "ban", "SEBI action",
    "stake sale", "FII selling", "pledged shares", "promoter selling",
]


def _classify_sentiment(text: str) -> str:
    """Classify a text as positive, negative, or neutral."""
    text_lower = text.lower()

    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw.lower() in text_lower)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw.lower() in text_lower)

    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    return "neutral"


def _get_news(symbol: str) -> List[Dict[str, Any]]:
    """Fetch recent news via the unified data provider."""
    from scraper.data_provider import get_stock_data

    data = get_stock_data(symbol)

    formatted = []
    for item in data.news[:15]:
        title = item.get("title", "")
        summary = item.get("summary", "")
        formatted.append({
            "title": title,
            "summary": summary,
            "text": f"{title} {summary}",
        })

    return formatted


def analyze_sentiment(symbol: str) -> Dict[str, Any]:
    """
    Analyze news sentiment for a ticker.
    Returns structured signal based on keyword-based sentiment scoring.
    """
    logger.info(f"[SENTIMENT] {symbol}: Fetching news from yfinance...")

    try:
        news_items = _get_news(symbol)

        if not news_items:
            logger.warning(f"[SENTIMENT] {symbol}: No news items found")
            return {
                "signal": AnalystSignal(
                    signal="neutral", confidence=20,
                    reasoning=f"No recent news found for {symbol}"
                ),
                "news_count": 0,
            }

        logger.info(f"[SENTIMENT] {symbol}: Found {len(news_items)} news items")
        for i, item in enumerate(news_items[:5]):
            logger.info(f"[SENTIMENT] {symbol}: News[{i}]: {item['title'][:80]}")

        # Score each news item
        sentiments = []
        for item in news_items:
            sentiment = _classify_sentiment(item["text"])
            sentiments.append(sentiment)

        positive_count = sentiments.count("positive")
        negative_count = sentiments.count("negative")
        neutral_count = sentiments.count("neutral")
        total = len(sentiments)

        # Calculate net sentiment score (-1 to +1)
        net_score = (positive_count - negative_count) / total if total > 0 else 0

        # Determine signal
        if net_score > 0.2:
            signal = "bullish"
        elif net_score < -0.2:
            signal = "bearish"
        else:
            signal = "neutral"

        confidence = min(abs(net_score) * 100 + 20, 85)  # Base 20% + sentiment strength

        reasoning = (
            f"{total} news items: {positive_count} positive, {negative_count} negative, "
            f"{neutral_count} neutral. Net sentiment score: {net_score:.2f}"
        )

        # Include top headline in reasoning
        if news_items:
            top_headline = news_items[0]["title"][:60]
            reasoning += f". Latest: '{top_headline}...'"

        return {
            "signal": AnalystSignal(
                signal=signal, confidence=confidence, reasoning=reasoning
            ),
            "news_count": total,
            "positive": positive_count,
            "negative": negative_count,
        }

    except Exception as e:
        logger.error(f"Sentiment analysis failed for {symbol}: {e}")
        return {
            "signal": AnalystSignal(
                signal="neutral", confidence=0,
                reasoning=f"Sentiment error: {str(e)[:80]}"
            ),
            "news_count": 0,
        }
