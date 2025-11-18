import asyncio
import os
import logging
from dotenv import load_dotenv
from app.jobs import StockAnalysisJob

# Load environment variables
load_dotenv()

# Configure logging to see what's happening
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_stock_analysis():
    """
    Test the StockAnalysisJob with a sample ticker.
    """
    # Get API keys from environment
    newsapi_key = os.getenv("NEWSAPI_KEY")
    if not newsapi_key:
        print("Error: NEWSAPI_KEY not found in environment variables")
        print("Please create a .env file with your NewsAPI key")
        print("Get your free key at: https://newsapi.org/register")
        return

    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if not finnhub_key:
        print("Error: FINNHUB_API_KEY not found in environment variables")
        print("Please add your Finnhub API key to .env file")
        print("Get your free key at: https://finnhub.io/register")
        return

    ticker = "BABA"
    company_name = "Alibaba"
    job = StockAnalysisJob(
        job_id=f"test_job_{ticker}",
        ticker=ticker,
        company_name=company_name,
        newsapi_key=newsapi_key,
        finnhub_key=finnhub_key
    )
    result = await job.execute()

    if result['status'] == 'COMPLETED':
        job_result = result['result']
        print(f"\n{'='*60}")
        print(f"Stock Analysis Results for {job_result['ticker']}")
        print(f"{'='*60}")
        print(f"\nArticles Found: {job_result['articles_found']}")
        print(f"Sentiment: {job_result['sentiment_label']} "
              f"(score: {job_result['sentiment_score']})")
        print(f"Summary: {job_result['summary'] or 'Not yet implemented'}")

    else:
        print(f"\nError: {result['error']}")


if __name__ == "__main__":
    asyncio.run(test_stock_analysis())