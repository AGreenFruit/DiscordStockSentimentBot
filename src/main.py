import asyncio
import logging
import os
import discord
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.bot.discord_bot import bot
from app.jobs.stock_tracker_job import StockTrackerJob

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def run_stock_tracker():
    try:
        job = StockTrackerJob(
            newsapi_key=os.getenv("NEWSAPI_KEY"),
            finnhub_key=os.getenv("FINNHUB_API_KEY"),
            bot=bot
        )
        await job.execute()
    except Exception as e:
        logger.error(f"Stock tracker error: {e}", exc_info=True)


@bot.event
async def on_ready():
    logger.info(f'{bot.user} connected')
    
    await bot.change_presence(
        activity=discord.Game(name="!commands for help")
    )

    if not scheduler.running:
        scheduler.add_job(
            run_stock_tracker,
            trigger=IntervalTrigger(hours=1),
            id='stock_tracker_job',
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started (hourly)")
        await run_stock_tracker()


async def main():
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN required")

    try:
        await bot.start(token)
    finally:
        if scheduler.running:
            scheduler.shutdown()
        await bot.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped")