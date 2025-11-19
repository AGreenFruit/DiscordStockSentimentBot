# 📊 Stock Analysis Discord Bot

Automated stock sentiment analysis bot that scrapes news, analyzes sentiment using FinBERT, generates summaries with DistilBART, and sends Discord notifications to subscribers.

## Features

- 🤖 Discord Bot with auto-validation
- 🔍 Smart ticker search
- 📰 Multi-source news (NewsAPI, Yahoo Finance, Finnhub)
- 🧠 FinBERT sentiment analysis
- 📝 DistilBART summarization
- ⏰ Hourly scheduled updates
- 💾 PostgreSQL database
- 📬 DM notifications

## Setup

### 1. Install Dependencies
```bash
uv sync
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```env
NEWSAPI_KEY=your_key                    # https://newsapi.org/register
FINNHUB_API_KEY=your_key                # https://finnhub.io/register
DISCORD_BOT_TOKEN=your_token            # https://discord.com/developers

DB_NAME=stock_analysis
DB_USER=your_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
```

### 3. Set Up PostgreSQL Database
```sql
CREATE DATABASE stock_analysis;
CREATE SCHEMA stock_analysis;

CREATE TABLE stock_analysis.stocks (
    ticker VARCHAR(10) PRIMARY KEY,
    company_name VARCHAR(255) NOT NULL,
    last_analysis_timestamp TIMESTAMP,
    last_sentiment_score FLOAT
);

CREATE TABLE stock_analysis.user_stock_subscriptions (
    hash VARCHAR(50) PRIMARY KEY,
    discord_id VARCHAR(50),
    ticker VARCHAR(50),
    company_name VARCHAR(50),
    FOREIGN KEY (ticker) REFERENCES stock_analysis.stocks(ticker)
);
```

### 4. Set Up Discord Bot
1. Go to https://discord.com/developers/applications
2. Create new application → Bot tab → Add Bot
3. Enable "MESSAGE CONTENT INTENT"
4. Copy token to `.env`
5. OAuth2 → URL Generator → Select `bot` scope
6. Permissions: Send Messages, Embed Links, Read Message History
7. Invite bot to your server

### 5. Run
```bash
uv run python src/main.py
```

## Commands

| Command | Description |
|---------|-------------|
| `!subscribe TICKER` | Subscribe with auto-validation |
| `!search QUERY` | Search for tickers |
| `!unsubscribe TICKER` | Unsubscribe from stock |
| `!mystocks` | List your subscriptions |
| `!stockinfo TICKER` | Get latest analysis |
| `!commands` | Show all commands |

## How It Works

1. **Subscribe**: `!subscribe NVDA` → Bot validates ticker and subscribes you
2. **Hourly Analysis**: Bot scrapes news, analyzes sentiment, generates summaries
3. **Notifications**: Receive DM with sentiment score and summary
4. **Check Anytime**: `!stockinfo NVDA` to see latest analysis

## Configuration

**Change frequency** (edit `src/main.py`):
```python
trigger=IntervalTrigger(hours=1)  # Default: hourly
```

**Adjust sentiment thresholds** (edit `src/app/services/sentiment_analyzer.py`):
```python
if sentiment_score >= 0.15:  # Positive
elif sentiment_score <= -0.15:  # Negative
```