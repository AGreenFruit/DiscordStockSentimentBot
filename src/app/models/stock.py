"""Pydantic models for stock data"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Stock(BaseModel):
    """Stock model for database storage"""
    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str = Field(..., description="Company name")
    last_analysis_timestamp: Optional[datetime] = Field(
        None,
        description="Timestamp of last analysis"
    )
    last_sentiment_score: Optional[float] = Field(
        None,
        description="Last sentiment score (-1 to 1)"
    )
    last_sentiment_label: Optional[str] = Field(
        None,
        description="Last sentiment label (positive/negative/neutral)"
    )
    last_summary: Optional[str] = Field(
        None,
        description="Last generated summary"
    )
    articles_count: Optional[int] = Field(
        None,
        description="Number of articles analyzed"
    )


class UserStockSubscription(BaseModel):
    """User stock subscription model"""
    discord_id: str = Field(..., description="Discord user ID")
    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str = Field(..., description="Company name")
    subscribed_at: datetime = Field(
        default_factory=datetime.now,
        description="Subscription timestamp"
    )
