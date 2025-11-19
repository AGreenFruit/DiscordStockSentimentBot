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


class UserStockSubscription(BaseModel):
    """User stock subscription model"""
    hash: str = Field(..., description="Hash of discord_id:ticker")
    discord_id: str = Field(..., description="Discord user ID")
    ticker: str = Field(..., description="Stock ticker symbol")
    company_name: str = Field(..., description="Company name")
