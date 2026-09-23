# scrape-indonesia-trends

Automated scraper for Indonesian news trending topics (Detik Terpopuler and Kompas Tren) with deduplication and Discord webhook notifications.

## Requirements
- Python 3.10+
- `httpx`
- `beautifulsoup4`

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running
```bash
export DISCORD_TRENDS_WEBHOOK_URL="https://discord.com/api/webhooks/..."
python scripts/scrape_trends.py
```
