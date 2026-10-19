import yfinance as yf
import feedparser
import requests
import time
import hashlib
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# ====================== SETTINGS ======================
TELEGRAM_TOKEN = "7863867994:AAG4SgFIu-zl4GHz30cUkZBPe_9Y97st7Fw"
TELEGRAM_CHAT_ID = "1924745245"

WATCHLIST = [
    # Big stocks
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD", "NFLX", "INTC",
    "BABA", "SOFI", "PLTR", "RIVN", "LCID", "NIO", "XPEV", "LI",
    
    # Popular / volatile smaller stocks & pennies
    "SNDL", "CTRM", "BBIG", "MULN", "FFIE", "GME", "AMC", "BB", "NOK",
    "DNA", "OPEN", "HOOD", "COIN", "MARA", "RIOT", "CLSK", "HUT", "BITF",

    # Your tickers
    "TWG", "FUFU", "SAFX", "MDHX"
]

PRICE_MOVE_PERCENT = 5.0
VOLUME_SPIKE_MULTIPLIER = 3.0
CHECK_INTERVAL_MINUTES = 6

CONTRACT_KEYWORDS = [
    "contract", "award", "awarded", "agreement", "deal", "partnership",
    "loi", "letter of intent", "mou", "memorandum", "purchase order",
    "supply agreement", "service agreement", "collaboration", "signed",
    "secures", "wins contract", "new contract", "major contract",
    "commercial agreement", "strategic partnership", "binding agreement"
]

IMPORTANT_KEYWORDS = CONTRACT_KEYWORDS + [
    "earnings", "guidance", "upgrade", "downgrade", "fda", "approval",
    "clinical", "dilution", "offering", "reverse split", "halt",
    "lawsuit", "sec investigation", "short squeeze", "buyout", "acquisition"
]
# ======================================================

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
            return None

        current_price = hist["Close"].iloc[-1]
        prev_close = hist["Close"].iloc[-2]
        current_volume = hist["Volume"].iloc[-1]
        avg_volume = hist["Volume"].iloc[:-1].mean()

        change_pct = ((current_price - prev_close) / prev_close) * 100
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        is_strong_move = abs(change_pct) >= PRICE_MOVE_PERCENT
        is_volume_spike = volume_ratio >= VOLUME_SPIKE_MULTIPLIER

        result = {
            "ticker": ticker,
            "price": current_price,
            "change_pct": change_pct,
            "volume_ratio": volume_ratio,
            "is_strong_move": is_strong_move,
            "is_volume_spike": is_volume_spike
        }

        if is_strong_move or is_volume_spike:
            direction = "🟢 UP" if change_pct > 0 else "🔴 DOWN"
            vol_text = f"{volume_ratio:.1f}x volume" if is_volume_spike else "Normal volume"

            msg = (
                f"<b>{direction} {ticker}</b>\n"
                f"Price: ${current_price:.4f}\n"
                f"Change: <b>{change_pct:+.2f}%</b>\n"
                f"{vol_text}\n"
                f"Time: {datetime.now().strftime('%H:%M')}"
            )
            send_telegram(msg)

        return result

    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def check_news_and_signal(ticker, price_data):
    try:
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
        feed = feedparser.parse(rss_url)

        best_score = 0
        best_title = ""
        is_contract_news = False

        for entry in feed.entries[:6]:
            title = entry.get("title", "")
            summary = entry.get("summary", "") or ""
            link = entry.get("link", "")

            article_id = get_article_id(title, link)
            if article_id in seen_news:
                continue

            full_text = f"{title}. {summary}"
            score = analyze_sentiment(full_text)

            is_contract = contains_keywords(full_text, CONTRACT_KEYWORDS)
            is_important = contains_keywords(full_text, IMPORTANT_KEYWORDS)

            if is_contract or is_important or abs(score) >= 0.35:
                seen_news.add(article_id)

                if abs(score) > abs(best_score):
                    best_score = score
                    best_title = title
                    is_contract_news = is_contract

                if is_contract:
                    tag = "📝 PRE-CONTRACT / DEAL"
                elif score >= 0.35:
                    tag = "🟢 POSITIVE NEWS"
                elif score <= -0.35:
                    tag = "🔴 NEGATIVE NEWS"
                else:
                    tag = "⚠️ IMPORTANT NEWS"

                msg = (
                    f"<b>{tag} — {ticker}</b>\n\n"
                    f"<b>{title}</b>\n\n"
                    f"{summary[:160]}...\n\n"
                    f"<a href='{link}'>Read full article</a>\n"
                    f"Sentiment: {score:+.2f}"
                )
                send_telegram(msg)

        # ========== BUY / SELL SIGNAL LOGIC ==========
        if price_data is None:
            return

        change = price_data["change_pct"]
        vol_ratio = price_data["volume_ratio"]
        price = price_data["price"]

        # BUY Signal
        if change >= 5 and vol_ratio >= 2.5 and best_score > 0.25:
            signal_msg = (
                f"<b>🟢 BUY SIGNAL — {ticker}</b>\n\n"
                f"Price: ${price:.4f}\n"
                f"Change: <b>+{change:.2f}%</b>\n"
                f"Volume: {vol_ratio:.1f}x\n"
                f"News Sentiment: {best_score:+.2f}\n"
            )
            if is_contract_news:
                signal_msg += "📝 Contract/Deal news detected\n"
            signal_msg += "\n<i>This is an automated signal, not financial advice.</i>"
            send_telegram(signal_msg)

        # SELL Signal
        elif change <= -5 and vol_ratio >= 2.5 and best_score < -0.25:
            signal_msg = (
                f"<b>🔴 SELL SIGNAL — {ticker}</b>\n\n"
                f"Price: ${price:.4f}\n"
                f"Change: <b>{change:.2f}%</b>\n"
                f"Volume: {vol_ratio:.1f}x\n"
                f"News Sentiment: {best_score:+.2f}\n"
                f"\n<i>This is an automated signal, not financial advice.</i>"
            )
            send_telegram(signal_msg)

    except Exception as e:
        print(f"News/Signal error {ticker}: {e}")

def main():
    send_telegram(
        "✅ <b>Smart Stock Alert Bot Started</b>\n"
        "Features:\n"
        "• Price & Volume alerts\n"
        "• Pre-contract / Deal news\n"
        "• Buy / Sell signals\n\n"
        "<i>Signals are automated and NOT financial advice.</i>"
    )

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Checking...")
        
        for ticker in WATCHLIST:
            price_data = check_price_and_volume(ticker)
            if price_data and (price_data["is_strong_move"] or price_data["is_volume_spike"]):
                check_news_and_signal(ticker, price_data)
            time.sleep(0.9)

        print(f"Sleeping {CHECK_INTERVAL_MINUTES} minutes...")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)

if __name__ == "__main__":
    main()