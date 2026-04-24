import os
import json
import logging
import time
from datetime import datetime
from typing import List

import praw
from newsapi import NewsApiClient
import requests
from apscheduler.schedulers.background import BackgroundScheduler

from database import init_db, record_sentiment, get_config, set_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sentinel_worker")

REDDIT_CID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_AGENT = os.getenv("REDDIT_USER_AGENT")
NEWS_KEY = os.getenv("NEWS_API_KEY")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://192.168.1.100:11434")
WATCHLIST = [t.strip().upper() for t in os.getenv("WATCHLIST", "AAPL,MSFT,NVDA,TSLA,AMZN").split(",") if t.strip()]
SUBREDDITS = [s.strip() for s in os.getenv("SUBREDDITS", "wallstreetbets,stocks,investing").split(",") if s.strip()]

reddit = None
if REDDIT_CID and REDDIT_SECRET and REDDIT_AGENT:
    reddit = praw.Reddit(client_id=REDDIT_CID, client_secret=REDDIT_SECRET, user_agent=REDDIT_AGENT)
else:
    logger.warning("Reddit credentials not fully configured. Skipping Reddit scraping.")

newsapi = None
if NEWS_KEY:
    newsapi = NewsApiClient(api_key=NEWS_KEY)
else:
    logger.warning("NewsAPI key not configured. Skipping news scraping.")

TOOLS_DEF = [
    {
        "type": "function",
        "function": {
            "name": "record_sentiment",
            "description": "Record the sentiment analysis result for a stock ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "Stock ticker symbol"
                    },
                    "score": {
                        "type": "number",
                        "description": "Sentiment score from -1.0 (very bearish) to 1.0 (very bullish)"
                    },
                    "catalyst": {
                        "type": "string",
                        "description": "Brief summary of the key catalyst or reason for the sentiment"
                    },
                    "confidence": {
                        "type": "number",
                        "description": "Confidence in the score from 0.0 to 1.0"
                    }
                },
                "required": ["ticker", "score", "catalyst", "confidence"]
            }
        }
    }
]


def get_active_model() -> str:
    model = get_config("selected_model")
    if not model:
        model = os.getenv("INITIAL_MODEL", "llama3.1")
    return model


def fetch_reddit(ticker: str, limit: int = 10) -> List[str]:
    texts = []
    if not reddit:
        return texts
    try:
        for sub in SUBREDDITS:
            for post in reddit.subreddit(sub).search(ticker, sort="new", time_filter="day", limit=limit):
                texts.append(f"{post.title}. {post.selftext}")
    except Exception as e:
        logger.error(f"Reddit fetch error for {ticker}: {e}")
    return texts


def fetch_news(ticker: str, page_size: int = 5) -> List[str]:
    texts = []
    if not newsapi:
        return texts
    try:
        articles = newsapi.get_everything(q=ticker, language="en", sort_by="publishedAt", page_size=page_size)
        for a in articles.get("articles", []):
            texts.append(f"{a['title']}. {a['description'] or ''}")
    except Exception as e:
        logger.error(f"NewsAPI fetch error for {ticker}: {e}")
    return texts


def analyze_with_ollama(ticker: str, context: str):
    model = get_active_model()
    prompt = (
        f"You are a financial sentiment analyst. Based on the following recent Reddit and news context for {ticker}, "
        f"determine the overall market sentiment. Use the record_sentiment tool to save your analysis.\n\n"
        f"Context:\n{context}\n\n"
        f"Call the record_sentiment function with the ticker, a score between -1.0 and 1.0, a concise catalyst, and your confidence (0.0-1.0)."
    )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "tools": TOOLS_DEF,
        "stream": False,
        "options": {"temperature": 0.2}
    }
    try:
        resp = requests.post(f"{OLLAMA_HOST}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        message = data.get("message", {})
        tool_calls = message.get("tool_calls", [])
        if not tool_calls:
            logger.warning(f"No tool call returned for {ticker}. Model response: {message.get('content')}")
            return
        for tc in tool_calls:
            fn = tc.get("function", {})
            if fn.get("name") == "record_sentiment":
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    args = json.loads(args)
                logger.info(f"Tool call for {ticker}: {args}")
                record_sentiment(
                    ticker=args.get("ticker", ticker),
                    score=args.get("score"),
                    catalyst=args.get("catalyst", "No catalyst provided"),
                    confidence=args.get("confidence", 0.0)
                )
    except Exception as e:
        logger.error(f"Ollama analysis error for {ticker}: {e}")


def run_analysis():
    logger.info("Starting analysis run...")
    for ticker in WATCHLIST:
        reddit_texts = fetch_reddit(ticker)
        news_texts = fetch_news(ticker)
        all_texts = reddit_texts + news_texts
        if not all_texts:
            logger.info(f"No data gathered for {ticker}, skipping.")
            continue
        context = "\n".join(all_texts)[:4000]
        analyze_with_ollama(ticker, context)
        time.sleep(1)
    logger.info("Analysis run complete.")


def main():
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_analysis, "interval", hours=4)
    scheduler.start()
    logger.info("Worker started. Running initial analysis...")
    run_analysis()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Shutting down worker...")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
