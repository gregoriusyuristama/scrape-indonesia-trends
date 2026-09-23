import unittest
from unittest.mock import patch
from scripts.scrape_trends import scrape_detik, scrape_kompas, send_discord_webhook

SAMPLE_DETIK_HTML = """
<html>
<body>
    <article>
        <div class="media__title">
            <a href="https://news.detik.com/berita/123/sample-news">Sample Detik News</a>
        </div>
    </article>
</body>
</html>
"""

SAMPLE_KOMPAS_HTML = """
<html>
<body>
    <a href="https://www.kompas.com/tren/read/2026/09/23/123/sample-kompas-tren">
        Sample Kompas Tren Article Title Longer Than 20 Characters
    </a>
</body>
</html>
"""

class TestScrapeTrends(unittest.TestCase):
    def test_scrape_detik_parses_articles(self):
        with patch("scripts.scrape_trends.fetch_with_retry", return_value=SAMPLE_DETIK_HTML):
            results = scrape_detik()
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["title"], "Sample Detik News")
            self.assertEqual(results[0]["url"], "https://news.detik.com/berita/123/sample-news")
            self.assertEqual(results[0]["source"], "Detik")

    def test_scrape_kompas_parses_articles(self):
        with patch("scripts.scrape_trends.fetch_with_retry", return_value=SAMPLE_KOMPAS_HTML):
            results = scrape_kompas()
            self.assertEqual(len(results), 1)
            self.assertIn("Sample Kompas Tren Article Title", results[0]["title"])
            self.assertEqual(results[0]["url"], "https://www.kompas.com/tren/read/2026/09/23/123/sample-kompas-tren")
            self.assertEqual(results[0]["source"], "Kompas")

    def test_send_discord_webhook_empty_url(self):
        res = send_discord_webhook(None, [], [])
        self.assertFalse(res)

if __name__ == "__main__":
    unittest.main()
