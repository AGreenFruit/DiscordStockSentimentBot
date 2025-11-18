import aiohttp
import trafilatura
from typing import Optional, List
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class ArticleContentFetcher:
    """
    Service for fetching full article content from URLs.
    """

    def __init__(self, max_concurrent: int = 5):
        """
        Initialize the content fetcher.

        Args:
            max_concurrent: Maximum concurrent requests
        """
        self.max_concurrent = max_concurrent
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Context manager entry."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.session:
            await self.session.close()

    async def fetch_article_content(
        self,
        article: NewsArticle
    ) -> NewsArticle:
        """
        Fetch full content for a single article.

        Args:
            article: NewsArticle object with URL

        Returns:
            Updated NewsArticle with full content
        """
        if not article.url or not article.url.startswith('http'):
            logger.debug(f"Skipping invalid URL: {article.url}")
            return article

        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }

            async with self.session.get(
                article.url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.debug(
                        f"Failed to fetch {article.url}: "
                        f"status {response.status}"
                    )
                    return article

                html = await response.text()

                # Extract main content using trafilatura
                content = trafilatura.extract(
                    html,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False
                )

                if content and len(content) > 100:
                    article.content = content
                    logger.debug(
                        f"Extracted {len(content)} chars from {article.url}"
                    )
                else:
                    logger.debug(
                        f"No content extracted from {article.url}"
                    )

                return article

        except aiohttp.ClientError as e:
            logger.debug(f"Network error fetching {article.url}: {e}")
            return article
        except Exception as e:
            logger.debug(f"Error fetching {article.url}: {e}")
            return article

    async def fetch_multiple_contents(
        self,
        articles: List[NewsArticle]
    ) -> List[NewsArticle]:
        """
        Fetch content for multiple articles concurrently.

        Args:
            articles: List of NewsArticle objects

        Returns:
            List of updated NewsArticle objects with content
        """
        import asyncio

        logger.info(f"Fetching content for {len(articles)} articles")

        # Process in batches to avoid overwhelming servers
        updated_articles = []
        for i in range(0, len(articles), self.max_concurrent):
            batch = articles[i:i + self.max_concurrent]
            tasks = [
                self.fetch_article_content(article)
                for article in batch
            ]
            batch_results = await asyncio.gather(*tasks)
            updated_articles.extend(batch_results)

        # Count successful fetches
        success_count = sum(
            1 for article in updated_articles
            if article.content and len(article.content) > 100
        )

        logger.info(
            f"Successfully fetched content for {success_count}/"
            f"{len(articles)} articles"
        )

        return updated_articles

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
