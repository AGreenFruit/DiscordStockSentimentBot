import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class NewsScraper:
    """
    Service for scraping news articles using NewsAPI.
    """

    BASE_URL = "https://newsapi.org/v2/everything"

    def __init__(self, api_key: str):
        """
        Initialize the news scraper.

        Args:
            api_key: NewsAPI API key
        """
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.session:
            await self.session.close()

    async def search_news(
        self,
        ticker: str,
        company_name: str = None,
        hours_back: int = 12,
        max_articles: int = 15
    ) -> List[NewsArticle]:
        """
        Search for news articles related to a stock ticker.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            company_name: Company name (e.g., 'Apple')
            hours_back: How many hours back to search
            max_articles: Maximum number of articles to return

        Returns:
            List of NewsArticle objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        # Calculate time range
        to_time = datetime.now(timezone.utc)
        from_time = to_time - timedelta(hours=hours_back)

        # Build search query - use company name if provided
        search_query = company_name if company_name else ticker

        # Build query parameters
        params = {
            "q": search_query,
            "from": from_time.isoformat(),
            "to": to_time.isoformat(),
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": max_articles,
            "apiKey": self.api_key
        }

        try:
            logger.info(
                f"Fetching news for {ticker} (query: '{search_query}') "
                f"from last {hours_back} hours"
            )

            async with self.session.get(
                self.BASE_URL,
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(
                        f"NewsAPI error (status {response.status}): "
                        f"{error_text}"
                    )
                    return []

                data = await response.json()

                if data.get("status") != "ok":
                    logger.error(f"NewsAPI returned error: {data}")
                    return []

                total_results = data.get("totalResults", 0)
                logger.info(
                    f"NewsAPI returned {total_results} total results "
                    f"for {ticker}"
                )

                articles = self._parse_articles(data.get("articles", []))
                logger.info(f"Parsed {len(articles)} articles for {ticker}")

                return articles

        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return []

    def _parse_articles(self, raw_articles: List[dict]) -> List[NewsArticle]:
        """
        Parse raw article data from NewsAPI into NewsArticle objects.

        Args:
            raw_articles: List of article dictionaries from NewsAPI

        Returns:
            List of NewsArticle objects
        """
        articles = []

        for article_data in raw_articles:
            try:
                # Parse published date
                published_str = article_data.get("publishedAt")
                if published_str:
                    published_at = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00")
                    )
                else:
                    published_at = datetime.now(timezone.utc)

                # Create NewsArticle object
                article = NewsArticle(
                    title=article_data.get("title", ""),
                    description=article_data.get("description"),
                    content=article_data.get("content"),
                    url=article_data.get("url", ""),
                    source=article_data.get("source", {}).get(
                        "name",
                        "Unknown"
                    ),
                    published_at=published_at,
                    author=article_data.get("author")
                )

                articles.append(article)

            except Exception as e:
                logger.warning(f"Error parsing article: {e}")
                continue

        return articles

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
