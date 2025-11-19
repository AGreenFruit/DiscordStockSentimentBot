"""Job that analyzes all tracked stocks and sends notifications"""
import asyncio
from typing import Dict, Any, List
import logging
import psycopg2
import os
from datetime import datetime
from dotenv import load_dotenv
import discord

from interfaces.job import Job
from app.jobs.stock_analysis_job import StockAnalysisJob
from app.database.tables import StocksTable, UserStockSubscriptionsTable
from app.models.stock import Stock

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


class StockTrackerJob(Job):
    """
    Job that:
    1. Gets all tracked tickers from database
    2. Runs analysis for each ticker
    3. Saves results to database
    4. Sends notifications to subscribed users
    """

    def __init__(
        self,
        job_id: str = "stock_tracker_job",
        newsapi_key: str = None,
        finnhub_key: str = None,
        bot=None
    ):
        super().__init__(job_id)
        self.newsapi_key = newsapi_key
        self.finnhub_key = finnhub_key
        self.bot = bot
        self.conn = None
        self.cursor = None

    async def setup_resources(self) -> None:
        """Setup database connection"""
        self.conn = psycopg2.connect(
            dbname=os.getenv("DB_NAME", "stock_analysis"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
        )
        self.cursor = self.conn.cursor()

        # Initialize table abstractions
        self.stocks_table = StocksTable(self.conn, self.cursor)
        self.subscriptions_table = UserStockSubscriptionsTable(
            self.conn,
            self.cursor
        )

        # Register cleanup
        self.register_cleanup(self._close_db_connection)

    def _close_db_connection(self) -> None:
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    async def run_implementation(self) -> Dict[str, Any]:
        """Run analysis for all tracked stocks"""
        # Get all tracked tickers
        tracked_tickers = self.subscriptions_table.get_all_tracked_tickers()
        logger.info(f"Found {len(tracked_tickers)} tracked tickers")

        if not tracked_tickers:
            return {
                "tickers_processed": 0,
                "notifications_sent": 0,
                "message": "No tracked tickers"
            }

        results = []
        notifications_sent = 0

        for stock_info in tracked_tickers:
            ticker = stock_info['ticker']
            company_name = stock_info['company_name']

            try:
                logger.info(f"Analyzing {ticker}...")

                # Run stock analysis
                analysis_job = StockAnalysisJob(
                    job_id=f"analysis_{ticker}",
                    ticker=ticker,
                    company_name=company_name,
                    newsapi_key=self.newsapi_key,
                    finnhub_key=self.finnhub_key
                )

                result = await analysis_job.execute()

                if result['status'] == 'COMPLETED':
                    job_result = result['result']

                    # Save to database
                    stock = Stock(
                        ticker=ticker,
                        company_name=company_name,
                        last_analysis_timestamp=datetime.now(),
                        last_sentiment_score=job_result['sentiment_score']
                    )
                    self.stocks_table.upsert(stock)

                    # Send notifications to subscribers
                    if self.bot:
                        sent = await self._send_notifications(
                            ticker,
                            company_name,
                            job_result
                        )
                        notifications_sent += sent

                    results.append({
                        "ticker": ticker,
                        "status": "success",
                        "sentiment": job_result['sentiment_label'],
                        "articles": job_result['articles_found']
                    })

                    logger.info(
                        f"✓ {ticker}: {job_result['sentiment_label']} "
                        f"({job_result['articles_found']} articles)"
                    )
                else:
                    results.append({
                        "ticker": ticker,
                        "status": "failed",
                        "error": result.get('error', 'Unknown error')
                    })
                    logger.error(f"✗ {ticker}: {result.get('error')}")

            except Exception as e:
                logger.error(f"Error analyzing {ticker}: {e}")
                results.append({
                    "ticker": ticker,
                    "status": "error",
                    "error": str(e)
                })

        return {
            "tickers_processed": len(tracked_tickers),
            "successful": len([r for r in results if r['status'] == 'success']),
            "failed": len([r for r in results if r['status'] != 'success']),
            "notifications_sent": notifications_sent,
            "results": results
        }

    async def _send_notifications(
        self,
        ticker: str,
        company_name: str,
        analysis_result: Dict[str, Any]
    ) -> int:
        """Send notifications to all subscribers of a ticker"""
        try:
            # Get all subscribers
            discord_ids = self.subscriptions_table.get_subscribers_for_ticker(
                ticker
            )

            if not discord_ids:
                return 0

            # Determine sentiment color and emoji
            score = analysis_result['sentiment_score']
            if score >= 0.15:
                color = discord.Color.green()
                emoji = "📈"
            elif score <= -0.15:
                color = discord.Color.red()
                emoji = "📉"
            else:
                color = discord.Color.blue()
                emoji = "➡️"

            # Create embed
            embed = discord.Embed(
                title=f"{emoji} {ticker} - New Analysis Available",
                description=f"**{company_name}**",
                color=color
            )

            embed.add_field(
                name="Sentiment",
                value=f"{analysis_result['sentiment_label'].title()}",
                inline=True
            )

            embed.add_field(
                name="Score",
                value=f"{score:.3f}",
                inline=True
            )

            embed.add_field(
                name="Articles Analyzed",
                value=str(analysis_result['articles_found']),
                inline=True
            )

            if analysis_result.get('summary'):
                # Truncate summary if too long
                summary = analysis_result['summary']
                if len(summary) > 1024:
                    summary = summary[:1021] + "..."
                embed.add_field(
                    name="Summary",
                    value=summary,
                    inline=False
                )

            embed.set_footer(text=f"Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")

            # Send to all subscribers
            sent_count = 0
            for discord_id in discord_ids:
                try:
                    user = await self.bot.fetch_user(int(discord_id))
                    await user.send(embed=embed)
                    sent_count += 1
                    logger.info(f"Sent notification to user {discord_id}")
                except Exception as e:
                    logger.error(
                        f"Failed to send notification to {discord_id}: {e}"
                    )

            return sent_count

        except Exception as e:
            logger.error(f"Error sending notifications for {ticker}: {e}")
            return 0
