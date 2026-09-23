import os
import sys
import time
import logging
import sqlite3
from datetime import datetime
import httpx
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("TRENDS_DB_PATH", "trends_history.db")
WEBHOOK_URL = os.getenv("DISCORD_TRENDS_WEBHOOK_URL")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS seen_articles (
            url TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            scraped_at TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def is_seen(url):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM seen_articles WHERE url = ?", (url,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def mark_seen(articles):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for art in articles:
        cursor.execute(
            "INSERT OR IGNORE INTO seen_articles (url, source, title, scraped_at) VALUES (?, ?, ?, ?)",
            (art["url"], art["source"], art["title"], art["timestamp"])
        )
    conn.commit()
    conn.close()

def fetch_with_retry(url, retries=3, backoff=2):
    for attempt in range(retries):
        try:
            with httpx.Client(headers=HEADERS, timeout=10.0, follow_redirects=True) as client:
                res = client.get(url)
                res.raise_for_status()
                return res.text
        except Exception as e:
            logger.warning(f"Fetch failed for {url} (attempt {attempt+1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(backoff ** attempt)
            else:
                logger.error(f"Persistent failure fetching {url}")
                return None

def scrape_detik():
    url = "https://www.detik.com/terpopuler"
    html = fetch_with_retry(url)
    if not html:
        return []
    
    results = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        articles = soup.select("article")
        rank = 1
        for art in articles:
            title_el = art.select_one(".media__title a") or art.select_one("h3 a") or art.select_one("a")
            if not title_el:
                continue
            title = title_el.text.strip()
            link = title_el.get("href")
            if not link or not title:
                continue
            
            results.append({
                "rank": rank,
                "title": title,
                "url": link,
                "source": "Detik",
                "timestamp": datetime.utcnow().isoformat()
            })
            rank += 1
            if len(results) >= 10:
                break
    except Exception as e:
        logger.error(f"Error parsing Detik: {e}")
    return results

def scrape_kompas():
    url = "https://www.kompas.com/tren"
    html = fetch_with_retry(url)
    if not html:
        return []
    
    results = []
    try:
        soup = BeautifulSoup(html, "html.parser")
        seen_links = set()
        rank = 1
        for a in soup.find_all("a", href=True):
            raw_href = a.get("href")
            if not isinstance(raw_href, str):
                continue
            link = raw_href.split("?")[0]
            if "/tren/read/" in link and link not in seen_links:
                title = a.text.strip()
                lines = [l.strip() for l in title.split("\n") if l.strip()]
                cand_title = ""
                for line in lines:
                    if len(line) > 20 and not line.startswith("Dibaca"):
                        cand_title = line
                        break
                if not cand_title:
                    continue
                
                seen_links.add(link)
                results.append({
                    "rank": rank,
                    "title": cand_title,
                    "url": link,
                    "source": "Kompas",
                    "timestamp": datetime.utcnow().isoformat()
                })
                rank += 1
                if len(results) >= 10:
                    break
    except Exception as e:
        logger.error(f"Error parsing Kompas: {e}")
    return results

def send_discord_webhook(webhook_url, detik_trends, kompas_trends):
    if not webhook_url:
        logger.warning("No DISCORD_TRENDS_WEBHOOK_URL set. Skipping message post.")
        return False

    def build_field(trends):
        if not trends:
            return "No new articles found."
        lines = []
        for t in trends:
            lines.append(f"**#{t['rank']}** [{t['title']}]({t['url']})")
        return "\n".join(lines)[:1024]

    embed = {
        "title": "🇮🇩 Indonesian News Trending Digest",
        "description": f"Daily digest generated on {datetime.now().strftime('%Y-%m-%d %H:%M WIB')}",
        "color": 3447003,
        "fields": [
            {
                "name": "🔥 Detik Terpopuler",
                "value": build_field(detik_trends),
                "inline": False
            },
            {
                "name": "📈 Kompas Tren",
                "value": build_field(kompas_trends),
                "inline": False
            }
        ],
        "footer": {
            "text": "Automated Trends Scraper • CST-34"
        }
    }

    payload = {
        "embeds": [embed]
    }

    for attempt in range(5):
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(webhook_url, json=payload)
                if res.status_code == 429:
                    retry_after = float(res.json().get("retry_after", 1.0))
                    logger.warning(f"Rate limited by Discord. Retrying after {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                res.raise_for_status()
                logger.info("Successfully sent webhook.")
                return True
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            time.sleep(2 ** attempt)
    return False

def main():
    init_db()
    
    logger.info("Scraping Detik...")
    detik_all = scrape_detik()
    detik_new = [d for d in detik_all if not is_seen(d["url"])]

    logger.info("Scraping Kompas...")
    kompas_all = scrape_kompas()
    kompas_new = [k for k in kompas_all if not is_seen(k["url"])]

    logger.info(f"Detik: {len(detik_new)}/{len(detik_all)} new articles.")
    logger.info(f"Kompas: {len(kompas_new)}/{len(kompas_all)} new articles.")

    if not detik_new and not kompas_new:
        logger.info("No new articles from either source. Skipping post.")
        return

    send_discord_webhook(WEBHOOK_URL, detik_new, kompas_new)
    mark_seen(detik_new + kompas_new)
    logger.info("Finished run successfully.")

if __name__ == "__main__":
    main()
