"""Database package for stock analysis bot"""
from .tables import StocksTable, UserStockSubscriptionsTable

__all__ = [
    "StocksTable",
    "UserStockSubscriptionsTable"
]
