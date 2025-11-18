import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from logging import getLogger
from app.models import NewsArticle

logger = getLogger(__name__)


class YahooFinanceScraper:
    """
    Service for scraping news articles from Yahoo Finance.
    """

    def __init__(self):
        """Initialize the Yahoo Finance scraper."""
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
        hours_back: int = 12,
        max_articles: int = 15
    ) -> List[NewsArticle]:
        """
        Scrape news articles for a stock ticker from Yahoo Finance.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            hours_back: How many hours back to filter articles
            max_articles: Maximum number of articles to return

        Returns:
            List of NewsArticle objects
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        # Try the main quote page which includes news
        url = f"https://finance.yahoo.com/quote/{ticker}/"

        try:
            logger.info(
                f"Scraping Yahoo Finance news for {ticker}"
            )

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/91.0.4472.124 Safari/537.36"
                )
            }

            async with self.session.get(
                url,
                headers=headers,
                allow_redirects=True
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"Yahoo Finance returned status {response.status} "
                        f"for URL: {url}"
                    )
                    return []

                html = await response.text()
                logger.debug(f"Received {len(html)} bytes of HTML")
                articles = self._parse_articles(
                    html,
                    ticker,
                    hours_back,
                    max_articles
                )

                logger.info(
                    f"Scraped {len(articles)} articles from Yahoo Finance "
                    f"for {ticker}"
                )

                return articles

        except Exception as e:
            logger.error(f"Error scraping Yahoo Finance for {ticker}: {e}")
            return []

    def _parse_articles(
        self,
        html: str,
        ticker: str,
        hours_back: int,
        max_articles: int
    ) -> List[NewsArticle]:
        """
        Parse HTML to extract news articles.

        Args:
            html: HTML content from Yahoo Finance
            ticker: Stock ticker symbol
            hours_back: Filter articles within this time window
            max_articles: Maximum articles to return

        Returns:
            List of NewsArticle objects
        """
        soup = BeautifulSoup(html, 'lxml')
        articles = []
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)

        # Yahoo Finance news items - try multiple selectors
        news_items = []
        
        # Try finding list items with news
        news_items = soup.find_all('li', class_='stream-item')
        
        if not news_items:
            # Try finding all article tags
            news_items = soup.find_all('article')
        
        if not news_items:
            # Fallback: find all divs with links containing h3
            potential_items = soup.find_all('div')
            news_items = [
                item for item in potential_items
                if item.find('h3') and item.find('a')
            ]

        logger.info(f"Found {len(news_items)} potential news items")

        for item in news_items[:max_articles * 3]:  # Get extra for filtering
            try:
                article = self._parse_single_article(item, ticker)
                if article and article.title:
                    # Filter by time
                    if article.published_at >= cutoff_time:
                        articles.append(article)

                    if len(articles) >= max_articles:
                        break

            except Exception as e:
                logger.debug(f"Error parsing article item: {e}")
                continue

        return articles

    def _parse_single_article(
        self,
        item,
        ticker: str
    ) -> Optional[NewsArticle]:
        """
        Parse a single article element.

        Args:
            item: BeautifulSoup element
            ticker: Stock ticker symbol

        Returns:
            NewsArticle object or None
        """
        try:
            # Find title - try multiple approaches
            title_elem = item.find('h3')
            if not title_elem:
                # Try finding any heading
                title_elem = (
                    item.find('h2') or item.find('h4') or
                    item.find(class_='Fw(b)')
                )

            if not title_elem:
                return None

            # Extract title
            title = title_elem.get_text(strip=True)
            if not title or len(title) < 10:
                return None

            # Extract URL - be more aggressive in finding links
            link_elem = item.find('a')
            if not link_elem:
                # Try finding link within title element
                link_elem = title_elem.find_parent('a')

            url = ""
            if link_elem and link_elem.get('href'):
                url = link_elem['href']
                # Handle relative URLs
                if url.startswith('/'):
                    url = f"https://finance.yahoo.com{url}"
                elif not url.startswith('http'):
                    url = f"https://finance.yahoo.com/{url}"

            # Extract description
            desc_elem = item.find('p')
            description = desc_elem.get_text(strip=True) if desc_elem else None

            # Extract time - Yahoo uses relative times
            time_elem = (
                item.find('time') or
                item.find(class_='C($c-fuji-grey-j)')
            )
            published_at = self._parse_time(time_elem)

            # Extract source
            source_elem = item.find(class_='C($c-fuji-grey-j)')
            source = "Yahoo Finance"
            if source_elem:
                source_text = source_elem.get_text(strip=True)
                # Extract source name before bullet or time
                if '•' in source_text:
                    source = source_text.split('•')[0].strip()

            return NewsArticle(
                title=title,
                description=description,
                content=description,  # Yahoo doesn't provide full content
                url=url,
                source=source,
                published_at=published_at
            )

        except Exception as e:
            logger.debug(f"Error parsing single article: {e}")
            return None

    def _parse_time(self, time_elem) -> datetime:
        """
        Parse time element to datetime.

        Args:
            time_elem: BeautifulSoup time element

        Returns:
            datetime object
        """
        if not time_elem:
            return datetime.now(timezone.utc)

        try:
            time_text = time_elem.get_text(strip=True).lower()

            # Parse relative times
            now = datetime.now(timezone.utc)

            if 'hour' in time_text:
                hours = int(''.join(filter(str.isdigit, time_text)) or 1)
                return now - timedelta(hours=hours)
            elif 'minute' in time_text:
                minutes = int(''.join(filter(str.isdigit, time_text)) or 1)
                return now - timedelta(minutes=minutes)
            elif 'day' in time_text:
                days = int(''.join(filter(str.isdigit, time_text)) or 1)
                return now - timedelta(days=days)
            else:
                return now

        except Exception:
            return datetime.now(timezone.utc)

    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
