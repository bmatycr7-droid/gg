import yfinance as yf
import feedparser
import requests
import time
import hashlib
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ====================== YOUR SETTINGS ======================
TELEGRAM_TOKEN = "7863867994:AAG4SgFIu-zl4GHz30cUkZBPe_9Y97st7Fw"
TELEGRAM_CHAT_ID = "1924745245"

# Your stocks & penny stocks (change these later)
WATCHLIST = [
    "AAPL", "TSLA", "NVDA", "AMD", "SOFI",
    "SNDL", "CTRM", "NAKD", "GNUS", "IDEX"
]

PRICE_MOVE_PERCENT = 5.0          # 5%
VOLUME_SPIKE_MULTIPLIER = 3.0     # 3x average volume
CHECK_INTERVAL_MINUTES = 5

# Keywords especially important for pre-contract / deal news
CONTRACT_KEYWORDS = [
    "contract", "award", "awarded", "agreement", "deal", "partnership",
    "loi", "letter of intent", "mou", "memorandum", "purchase order",
    "supply agreement", "service agreement", "collaboration",
    "signed", "secures", "wins contract", "new contract", "major contract",
    "commercial agreement", "strategic partnership", "binding agreement"
]

IMPORTANT_KEYWORDS = CONTRACT_KEYWORDS + [
    "earnings", "guidance", "upgrade", "downgrade", "fda", "approval",
    "clinical", "dilution", "offering", "reverse split", "halt",
    "lawsuit", "sec investigation", "short squeeze"
]
# ===========================================================

analyzer = SentimentIntensityAnalyzer()
seen_news = set()

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

def get_article_id(title, link):
    return hashlib.md5(f"{title}{link}".encode()).hexdigest()

def analyze_sentiment(text):
    return analyzer.polarity_scores(text)["compound"]

def contains_keywords(text, keywords):
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)

def check_price_and_volume(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="5d", interval="1d")
        if len(hist) < 2:
            return

        current_price = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2]
        current_volume = hist["Volume"].iloc[-1]
        avg_volume = hist["Volume"].iloc[:-1].mean()

        change_pct = ((current_price - prev_close) / prev_close) * 100

        # Price move alert
        if abs(change_pct) >= PRICE_MOVE_PERCENT:
            direction = "🟢 UP" if change_pct > 0 else "🔴 DOWN"
            msg = (
                f"<b>{direction} {ticker}</b>\n"
                f"Price: ${current_price:.4f}\n"
                f"Change: <b>{change_pct:+.2f}%</b>\n"
                f"Time: {datetime.now().strftime('%H:%M')}"
            )
            send_telegram(msg)

        # Volume spike alert
        if avg_volume > 0 and current_volume >= avg_volume * VOLUME_SPIKE_MULTIPLIER:
            multiplier = current_volume / avg_volume
            msg = (
                f"<b>📊 VOLUME SPIKE {ticker}</b>\n"
                f"Current volume: {current_volume:,.0f}\n"
                f"Average: {avg_volume:,.0f}\n"
                f"<b>{multiplier:.1f}x</b> normal volume\n"
                f"Price: ${current_price:.4f} ({change_pct:+.2f}%)"
            )
            send_telegram(msg)

    except Exception as e:
        print(f"Price/Volume error {ticker}: {e}")

def check_news(ticker):
    try:
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries[:8]:
            title = entry.get("title", "")
            summary = entry.get("summary", "") or ""
            link = entry.get("link", "")
            published = entry.get("published", "")[:16]

            article_id = get_article_id(title, link)
            if article_id in seen_news:
                continue

            full_text = f"{title}. {summary}"
            score = analyze_sentiment(full_text)

            is_contract = contains_keywords(full_text, CONTRACT_KEYWORDS)
            is_important = contains_keywords(full_text, IMPORTANT_KEYWORDS)

            if is_contract or is_important or abs(score) >= 0.35:
                seen_news.add(article_id)

                if is_contract:
                    tag = "📝 PRE-CONTRACT / DEAL"
                    emoji = "📝"
                elif score >= 0.35:
                    tag = "POSITIVE NEWS"
                    emoji = "🟢"
                elif score <= -0.35:
                    tag = "NEGATIVE NEWS"
                    emoji = "🔴"
                else:
                    tag = "IMPORTANT NEWS"
                    emoji = "⚠️"

                msg = (
                    f"{emoji} <b>{tag} — {ticker}</b>\n\n"
                    f"<b>{title}</b>\n\n"
                    f"{summary[:200]}...\n\n"
                    f"<a href='{link}'>Read more</a>\n"
                    f"Sentiment: {score:+.2f} | {published}"
                )
                send_telegram(msg)

    except Exception as e:
        print(f"News error {ticker}: {e}")

def main():
    send_telegram("✅ <b>Stock Alert Bot Started</b>\nMonitoring your watchlist...")

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking...")
        for ticker in WATCHLIST:
            check_price_and_volume(ticker)
            check_news(ticker)
            time.sleep(1.5)

        print(f"Sleeping {CHECK_INTERVAL_MINUTES} minutes...")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()