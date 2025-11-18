import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class FinnhubScraper:
    """
    Service for fetching news articles from Finnhub API.
    """

    def __init__(self, api_key: str):
        """
        Initialize the Finnhub scraper.

        Args:
            api_key: Finnhub API key
        """
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.base_url = "https://finnhub.io/api/v1"

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
        hours_back: int = 12,
        max_articles: int = 15
    ) -> List[NewsArticle]:
        """
        Search for company news from Finnhub.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            hours_back: How many hours back to filter articles
            max_articles: Maximum number of articles to return

        Returns:
            List of NewsArticle objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        # Calculate date range
        to_date = datetime.now(timezone.utc)
        from_date = to_date - timedelta(hours=hours_back)

        # Format dates as YYYY-MM-DD
        from_str = from_date.strftime('%Y-%m-%d')
        to_str = to_date.strftime('%Y-%m-%d')

        # Finnhub company news endpoint
        url = f"{self.base_url}/company-news"
        params = {
            'symbol': ticker.upper(),
            'from': from_str,
            'to': to_str,
            'token': self.api_key
        }

        try:
            logger.info(
                f"Fetching Finnhub news for {ticker} "
                f"from {from_str} to {to_str}"
            )

            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(
                        f"Finnhub returned status {response.status}"
                    )
                    return []

                data = await response.json()

                if not isinstance(data, list):
                    logger.error("Unexpected Finnhub response format")
                    return []

                logger.info(
                    f"Finnhub returned {len(data)} total articles"
                )

                articles = self._parse_articles(
                    data,
                    ticker,
                    hours_back,
                    max_articles
                )

                logger.info(
                    f"Parsed {len(articles)} articles from Finnhub"
                )

                return articles

        except aiohttp.ClientError as e:
            logger.error(f"Network error fetching from Finnhub: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching Finnhub news for {ticker}: {e}")
            return []

    def _parse_articles(
        self,
        data: List[dict],
        ticker: str,
        hours_back: int,
        max_articles: int
    ) -> List[NewsArticle]:
        """
        Parse articles from Finnhub API response.

        Args:
            data: List of article dictionaries from API
            ticker: Stock ticker
            hours_back: Filter articles within this time window
            max_articles: Maximum articles to return

        Returns:
            List of NewsArticle objects
        """
        articles = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        for item in data:
            try:
                article = self._parse_single_article(item, ticker)
                if article and article.published_at >= cutoff_time:
                    articles.append(article)

                    if len(articles) >= max_articles:
                        break

            except Exception as e:
                logger.debug(f"Error parsing article: {e}")
                continue

        return articles

    def _parse_single_article(
        self,
        item: dict,
        ticker: str
    ) -> Optional[NewsArticle]:
        """
        Parse a single article from Finnhub API.

        Args:
            item: Article dictionary from API
            ticker: Stock ticker symbol

        Returns:
            NewsArticle object or None
        """
        try:
            # Extract fields from Finnhub response
            # Finnhub format: {
            #   "category": "company news",
            #   "datetime": 1234567890,
            #   "headline": "Article title",
            #   "id": 12345,
            #   "image": "url",
            #   "related": "AAPL",
            #   "source": "Reuters",
            #   "summary": "Article summary",
            #   "url": "https://..."
            # }

            title = item.get('headline', '').strip()
            if not title or len(title) < 10:
                return None

            url = item.get('url', '')
            if not url:
                return None

            # Parse Unix timestamp to datetime
            timestamp = item.get('datetime', 0)
            if timestamp:
                published_at = datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc
                )
            else:
                published_at = datetime.now(timezone.utc)

            description = item.get('summary', '').strip()
            source = item.get('source', 'Finnhub').strip()

            return NewsArticle(
                title=title,
                description=description,
                content=description,  # Will be fetched later
                url=url,
                source=source,
                published_at=published_at
            )

        except Exception as e:
            logger.debug(f"Error parsing single article: {e}")
            return None

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
