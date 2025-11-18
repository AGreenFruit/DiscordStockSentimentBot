from typing import Dict, Any, Optional
from interfaces import Job
from app.services import (
    NewsScraper,
    YahooFinanceScraper,
    FinnhubScraper,
    ArticleContentFetcher,
    SentimentAnalyzer,
    TextSummarizer
)
from app.models import NewsArticle
import os
from logging import getLogger

logger = getLogger(__name__)


class StockAnalysisJob(Job):
    """
    Job for analyzing stock news, sentiment, and generating summaries.
    """

    def __init__(
        self,
        job_id: str,
        ticker: str,
        company_name: str,
        newsapi_key: str,
        finnhub_key: str
    ):
        super().__init__(job_id)
        self.ticker = ticker
        self.company_name = company_name
        self.newsapi_key = newsapi_key
        self.finnhub_key = finnhub_key
        self.news_scraper: Optional[NewsScraper] = None
        self.yahoo_scraper: Optional[YahooFinanceScraper] = None
        self.finnhub_scraper: Optional[FinnhubScraper] = None
        self.content_fetcher: Optional[ArticleContentFetcher] = None
        self.sentiment_analyzer: Optional[SentimentAnalyzer] = None
        self.text_summarizer: Optional[TextSummarizer] = None
        self.articles: list[NewsArticle] = []

    async def setup_resources(self) -> None:
        """
        Setup resources needed for stock analysis.
        Initialize news scraper, sentiment analyzer, summarizer, etc.
        """
        logger.info(f"Setting up resources for {self.ticker}")
        self.news_scraper = NewsScraper(self.newsapi_key)
        await self.news_scraper.__aenter__()
        
        self.yahoo_scraper = YahooFinanceScraper()
        await self.yahoo_scraper.__aenter__()

        self.finnhub_scraper = FinnhubScraper(self.finnhub_key)
        await self.finnhub_scraper.__aenter__()
        
        self.content_fetcher = ArticleContentFetcher(max_concurrent=5)
        await self.content_fetcher.__aenter__()

        self.sentiment_analyzer = SentimentAnalyzer()
        # Model will be loaded on first use

        self.text_summarizer = TextSummarizer()
        # Model will be loaded on first use

        self.register_cleanup(self._cleanup_scrapers)

    async def _cleanup_scrapers(self) -> None:
        """Cleanup all scrapers."""
        if self.news_scraper:
            await self.news_scraper.close()
        if self.yahoo_scraper:
            await self.yahoo_scraper.close()
        if self.finnhub_scraper:
            await self.finnhub_scraper.close()
        if self.content_fetcher:
            await self.content_fetcher.close()

    async def cleanup_resources(self) -> None:
        """
        Cleanup resources after job completion.
        """
        await super().cleanup_resources()

    async def pre_run_hook(self) -> None:
        """
        Pre-run validation and setup.
        """
        logger.info(f"Starting analysis for ticker: {self.ticker}")

    async def post_run_hook(self) -> None:
        """
        Post-run cleanup and notifications.
        """
        # TODO: Send notifications, store results, etc.
        pass

    def _deduplicate_articles(
        self,
        articles: list[NewsArticle]
    ) -> list[NewsArticle]:
        """
        Remove duplicate articles based on title similarity.

        Args:
            articles: List of articles to deduplicate

        Returns:
            Deduplicated list of articles
        """
        seen_titles = set()
        unique_articles = []

        for article in articles:
            # Normalize title for comparison
            normalized_title = article.title.lower().strip()

            if normalized_title not in seen_titles:
                seen_titles.add(normalized_title)
                unique_articles.append(article)

        return unique_articles

    async def run_implementation(self) -> Dict[str, Any]:
        """
        Main job logic:
        1. Scrape news for the ticker
        2. Analyze sentiment
        3. Generate summary
        """
        # Step 1: Scrape news articles from NewsAPI
        if not self.news_scraper:
            raise RuntimeError("News scraper not initialized")

        self.articles = await self.news_scraper.search_news(
            ticker=self.ticker,
            company_name=self.company_name,
            hours_back=12,
            max_articles=15
        )

        logger.info(
            f"NewsAPI returned {len(self.articles)} articles for "
            f"{self.ticker}"
        )

        # Step 2: Fallback to Yahoo Finance if insufficient articles
        min_articles = 5
        if len(self.articles) < min_articles and self.yahoo_scraper:
            logger.info(
                f"Insufficient articles from NewsAPI, trying Yahoo Finance"
            )
            yahoo_articles = await self.yahoo_scraper.search_news(
                ticker=self.ticker,
                hours_back=12,
                max_articles=15
            )
            
            logger.info(
                f"Yahoo Finance returned {len(yahoo_articles)} articles"
            )
            
            # Combine and deduplicate articles
            self.articles.extend(yahoo_articles)
            self.articles = self._deduplicate_articles(self.articles)

        # Step 2b: Fallback to Finnhub if still insufficient
        if len(self.articles) < min_articles and self.finnhub_scraper:
            logger.info(
                f"Still insufficient articles, trying Finnhub"
            )
            finnhub_articles = await self.finnhub_scraper.search_news(
                ticker=self.ticker,
                hours_back=12,
                max_articles=15
            )
            
            logger.info(
                f"Finnhub returned {len(finnhub_articles)} articles"
            )
            
            # Combine and deduplicate articles
            self.articles.extend(finnhub_articles)
            self.articles = self._deduplicate_articles(self.articles)

        logger.info(
            f"Total: {len(self.articles)} articles for {self.ticker}"
        )

        # Step 3: Fetch full article content
        if self.articles and self.content_fetcher:
            logger.info("Fetching full article content...")
            self.articles = await self.content_fetcher.fetch_multiple_contents(
                self.articles
            )

        # Step 4: Analyze sentiment
        sentiment_results = []
        if self.articles and self.sentiment_analyzer:
            logger.info("Analyzing sentiment...")
            sentiment_results = self.sentiment_analyzer.analyze_multiple(
                self.articles
            )

            # Aggregate overall sentiment
            sentiment_label, sentiment_score = (
                self.sentiment_analyzer.aggregate_sentiment(sentiment_results)
            )

            logger.info(
                f"Overall sentiment: {sentiment_label} "
                f"(score: {sentiment_score:.3f})"
            )
        else:
            sentiment_score = 0.0
            sentiment_label = "neutral"

        # Step 5: Generate summary
        if self.articles and self.text_summarizer:
            logger.info("Generating summary...")
            summary = self.text_summarizer.create_brief_summary(
                self.articles,
                sentiment_label,
                sentiment_score
            )
            logger.info(f"Summary generated: {len(summary)} chars")
        else:
            summary = "No articles available for summarization."

        # Convert articles to dict format for JSON serialization
        articles_data = [
            {
                "title": article.title,
                "source": article.source,
                "url": article.url,
                "published_at": article.published_at.isoformat(),
                "has_content": bool(article.content and len(article.content) > 100),
                "content_preview": (
                    article.content[:200] if article.content else None
                )
            }
            for article in self.articles
        ]

        return {
            "ticker": self.ticker,
            "articles_found": len(self.articles),
            "sentiment_score": sentiment_score,
            "sentiment_label": sentiment_label,
            "summary": summary,
            "articles": articles_data
        }
