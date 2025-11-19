import discord
from discord.ext import commands
import psycopg2
import os
import asyncio
import logging

from app.database.tables import StocksTable, UserStockSubscriptionsTable
from app.services.ticker_validator import TickerValidator

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)


def get_db_connection():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "stock_analysis"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


@bot.event
async def on_ready():
    logger.info(f'{bot.user} connected to {len(bot.guilds)} guilds')


@bot.command(name='subscribe')
async def subscribe(ctx, ticker: str, *, company_name: str = None):
    try:
        ticker = ticker.upper()
        discord_id = str(ctx.author.id)
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if not finnhub_key:
            await ctx.send(
                "❌ Ticker validation unavailable. "
                "Please provide company name: `!subscribe TICKER Company Name`"
            )
            return

        async with TickerValidator(finnhub_key) as validator:
            ticker_info = await validator.validate_ticker(ticker)

            if not ticker_info:
                await ctx.send(
                    f"❌ Ticker **{ticker}** not found. "
                    f"Try `!search {ticker}` to find the correct ticker."
                )
                return

            actual_company = ticker_info["company_name"]

            if company_name:
                verification = await validator.verify_match(
                    ticker,
                    company_name
                )

                if not verification["match"]:
                    embed = discord.Embed(
                        title="⚠️ Company Name Mismatch",
                        description=(
                            f"The ticker **{ticker}** corresponds to:\n"
                            f"**{actual_company}**\n\n"
                            f"You entered: **{company_name}**"
                        ),
                        color=discord.Color.orange()
                    )
                    embed.add_field(
                        name="Confirm subscription?",
                        value=(
                            f"React with ✅ to subscribe to **{ticker}** "
                            f"({actual_company})\n"
                            "React with ❌ to cancel"
                        ),
                        inline=False
                    )
                    msg = await ctx.send(embed=embed)
                    await msg.add_reaction("✅")
                    await msg.add_reaction("❌")

                    def check(reaction, user):
                        return (
                            user == ctx.author and
                            str(reaction.emoji) in ["✅", "❌"] and
                            reaction.message.id == msg.id
                        )

                    try:
                        reaction, user = await bot.wait_for(
                            "reaction_add",
                            timeout=30.0,
                            check=check
                        )

                        if str(reaction.emoji) == "❌":
                            await ctx.send("❌ Subscription cancelled.")
                            return
                    except asyncio.TimeoutError:
                        await ctx.send(
                            "⏱️ Confirmation timeout. Subscription cancelled."
                        )
                        return

            company_name = actual_company

        conn = get_db_connection()
        cursor = conn.cursor()

        stocks_table = StocksTable(conn, cursor)
        stock_exists = stocks_table.find_one(ticker=ticker)

        if not stock_exists:
            from app.models.stock import Stock
            stock = Stock(
                ticker=ticker,
                company_name=company_name,
                last_analysis_timestamp=None,
                last_sentiment_score=None
            )
            stocks_table.upsert(stock)

        subscriptions_table = UserStockSubscriptionsTable(conn, cursor)
        success = subscriptions_table.subscribe(
            discord_id=discord_id,
            ticker=ticker,
            company_name=company_name
        )

        cursor.close()
        conn.close()

        if success:
            embed = discord.Embed(
                title="✅ Subscribed!",
                description=(
                    f"You're now subscribed to **{ticker}**\n"
                    f"{company_name}"
                ),
                color=discord.Color.green()
            )
            embed.add_field(
                name="Exchange",
                value=ticker_info.get("exchange", "N/A"),
                inline=True
            )
            if ticker_info.get("industry"):
                embed.add_field(
                    name="Industry",
                    value=ticker_info["industry"],
                    inline=True
                )
            embed.add_field(
                name="What's next?",
                value=(
                    "You'll receive notifications when new analysis "
                    "is available."
                ),
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="ℹ️ Already Subscribed",
                description=f"You're already subscribed to **{ticker}**",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in subscribe command: {e}", exc_info=True)
        await ctx.send(
            f"❌ Error subscribing to {ticker}. Please try again later."
        )


@bot.command(name='unsubscribe')
async def unsubscribe(ctx, ticker: str):
    try:
        ticker = ticker.upper()
        discord_id = str(ctx.author.id)

        conn = get_db_connection()
        cursor = conn.cursor()

        subscriptions_table = UserStockSubscriptionsTable(conn, cursor)
        success = subscriptions_table.unsubscribe(discord_id, ticker)

        cursor.close()
        conn.close()

        if success:
            embed = discord.Embed(
                title="✅ Unsubscribed",
                description=f"You've been unsubscribed from **{ticker}**",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="ℹ️ Not Subscribed",
                description=f"You weren't subscribed to **{ticker}**",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in unsubscribe command: {e}")
        await ctx.send(
            f"❌ Error unsubscribing from {ticker}. Please try again later."
        )


@bot.command(name='mystocks')
async def mystocks(ctx):
    try:
        discord_id = str(ctx.author.id)

        conn = get_db_connection()
        cursor = conn.cursor()

        subscriptions_table = UserStockSubscriptionsTable(conn, cursor)
        subscriptions = subscriptions_table.get_user_subscriptions(
            discord_id
        )

        cursor.close()
        conn.close()

        if subscriptions:
            embed = discord.Embed(
                title="📊 Your Subscribed Stocks",
                description=f"You're tracking {len(subscriptions)} stock(s)",
                color=discord.Color.blue()
            )

            for sub in subscriptions:
                embed.add_field(
                    name=f"{sub['ticker']}",
                    value=sub['company_name'],
                    inline=True
                )

            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="📊 Your Subscribed Stocks",
                description="You're not subscribed to any stocks yet.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Get started",
                value="Use `!subscribe TICKER Company Name` to subscribe",
                inline=False
            )
            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in mystocks command: {e}")
        await ctx.send(
            "❌ Error fetching your subscriptions. Please try again later."
        )


@bot.command(name='stockinfo')
async def stockinfo(ctx, ticker: str):
    try:
        ticker = ticker.upper()

        conn = get_db_connection()
        cursor = conn.cursor()

        stocks_table = StocksTable(conn, cursor)
        stock = stocks_table.find_one(ticker=ticker)

        cursor.close()
        conn.close()

        if stock and stock['last_analysis_timestamp']:
            # Determine sentiment color
            score = stock['last_sentiment_score']
            if score >= 0.15:
                color = discord.Color.green()
                sentiment_emoji = "📈"
            elif score <= -0.15:
                color = discord.Color.red()
                sentiment_emoji = "📉"
            else:
                color = discord.Color.blue()
                sentiment_emoji = "➡️"

            embed = discord.Embed(
                title=f"{sentiment_emoji} {ticker} - {stock['company_name']}",
                description="Latest Stock Analysis",
                color=color
            )

            embed.add_field(
                name="Sentiment Score",
                value=f"{score:.3f}",
                inline=True
            )

            embed.add_field(
                name="Last Updated",
                value=stock['last_analysis_timestamp'].strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
                inline=True
            )

            embed.add_field(
                name="📊 Subscribe",
                value=f"Use `!subscribe {ticker} {stock['company_name']}`",
                inline=False
            )

            await ctx.send(embed=embed)
        elif stock:
            embed = discord.Embed(
                title=f"📊 {ticker} - {stock['company_name']}",
                description="No analysis available yet.",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Coming soon",
                value=(
                    "Analysis will be available after the next "
                    "scheduled update."
                ),
                inline=False
            )
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(
                title="❌ Stock Not Found",
                description=f"**{ticker}** is not being tracked yet.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Subscribe to track",
                value=f"Use `!subscribe {ticker} Company Name`",
                inline=False
            )
            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in stockinfo command: {e}")
        await ctx.send(
            f"❌ Error fetching info for {ticker}. Please try again later."
        )


@bot.command(name='search')
async def search(ctx, *, query: str):
    try:
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        if not finnhub_key:
            await ctx.send("❌ Search unavailable - API key not configured.")
            return

        async with TickerValidator(finnhub_key) as validator:
            results = await validator.search_symbol(query)

            if not results:
                await ctx.send(
                    f"❌ No results found for **{query}**. "
                    "Try a different search term."
                )
                return

            embed = discord.Embed(
                title=f"🔍 Search Results for '{query}'",
                description=f"Found {len(results)} match(es)",
                color=discord.Color.blue()
            )

            for result in results:
                embed.add_field(
                    name=f"{result['ticker']}",
                    value=(
                        f"{result['company_name']}\n"
                        f"Type: {result['type']}\n"
                        f"`!subscribe {result['ticker']}`"
                    ),
                    inline=False
                )

            await ctx.send(embed=embed)

    except Exception as e:
        logger.error(f"Error in search command: {e}", exc_info=True)
        await ctx.send("❌ Error performing search. Please try again later.")


@bot.command(name='commands')
async def commands_list(ctx):
    embed = discord.Embed(
        title="📊 Stock Analysis Bot Commands",
        description="Track stocks and get sentiment analysis updates",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="!subscribe TICKER [Company Name]",
        value=(
            "Subscribe to stock updates (company name optional)\n"
            "Example: `!subscribe AAPL` or `!subscribe AAPL Apple Inc.`"
        ),
        inline=False
    )

    embed.add_field(
        name="!search QUERY",
        value=(
            "Search for stock tickers\n"
            "Example: `!search Tesla` or `!search TSLA`"
        ),
        inline=False
    )

    embed.add_field(
        name="!unsubscribe TICKER",
        value="Unsubscribe from a stock\nExample: `!unsubscribe AAPL`",
        inline=False
    )

    embed.add_field(
        name="!mystocks",
        value="List all your subscribed stocks",
        inline=False
    )

    embed.add_field(
        name="!stockinfo TICKER",
        value="Get latest analysis for a stock\nExample: `!stockinfo AAPL`",
        inline=False
    )

    await ctx.send(embed=embed)
