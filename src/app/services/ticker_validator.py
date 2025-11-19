"""Ticker validation and company name lookup service"""
import aiohttp
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class TickerValidator:
    """Validates ticker symbols and company names using Finnhub API"""

    def __init__(self, finnhub_key: str):
        self.finnhub_key = finnhub_key
        self.base_url = "https://finnhub.io/api/v1"
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def search_symbol(
        self,
        query: str
    ) -> List[Dict[str, str]]:
        """
        Search for ticker symbols or company names.

        Args:
            query: Ticker symbol or company name to search

        Returns:
            List of matches with ticker, company name, and type
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.base_url}/search"
            params = {
                "q": query.upper(),
                "token": self.finnhub_key
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    results = []

                    # Parse results
                    for item in data.get("result", [])[:5]:  # Top 5
                        # Filter for US stocks only
                        symbol = item.get("symbol", "")
                        if "." not in symbol and len(symbol) <= 5:
                            results.append({
                                "ticker": item.get("symbol", ""),
                                "company_name": item.get("description", ""),
                                "type": item.get("type", "")
                            })

                    return results
                else:
                    logger.error(
                        f"Finnhub search failed: {response.status}"
                    )
                    return []

        except Exception as e:
            logger.error(f"Error searching symbol: {e}")
            return []

    async def validate_ticker(
        self,
        ticker: str
    ) -> Optional[Dict[str, str]]:
        """
        Validate a ticker symbol and get company info.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dict with ticker and company_name if valid, None otherwise
        """
        if not self.session:
            self.session = aiohttp.ClientSession()

        try:
            url = f"{self.base_url}/stock/profile2"
            params = {
                "symbol": ticker.upper(),
                "token": self.finnhub_key
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()

                    # Check if we got valid data
                    if data and data.get("name"):
                        return {
                            "ticker": ticker.upper(),
                            "company_name": data.get("name", ""),
                            "exchange": data.get("exchange", ""),
                            "industry": data.get("finnhubIndustry", "")
                        }
                    else:
                        return None
                else:
                    logger.error(
                        f"Finnhub validation failed: {response.status}"
                    )
                    return None

        except Exception as e:
            logger.error(f"Error validating ticker: {e}")
            return None

    async def verify_match(
        self,
        ticker: str,
        company_name: str
    ) -> Dict[str, any]:
        """
        Verify if ticker and company name match.

        Args:
            ticker: Stock ticker symbol
            company_name: Company name

        Returns:
            Dict with:
            - match: bool (True if they match)
            - confidence: str (high/medium/low)
            - actual_company: str (actual company name for ticker)
            - suggestion: str (suggested correction if mismatch)
        """
        # Validate the ticker
        ticker_info = await self.validate_ticker(ticker)

        if not ticker_info:
            return {
                "match": False,
                "confidence": "none",
                "actual_company": None,
                "suggestion": f"Ticker '{ticker}' not found"
            }

        actual_company = ticker_info["company_name"]

        # Normalize for comparison
        ticker_normalized = ticker.upper().strip()
        company_normalized = company_name.lower().strip()
        actual_normalized = actual_company.lower().strip()

        # Check for exact match
        if company_normalized == actual_normalized:
            return {
                "match": True,
                "confidence": "high",
                "actual_company": actual_company,
                "suggestion": None
            }

        # Check for partial match (one contains the other)
        if (company_normalized in actual_normalized or
                actual_normalized in company_normalized):
            return {
                "match": True,
                "confidence": "medium",
                "actual_company": actual_company,
                "suggestion": None
            }

        # Check for common abbreviations
        # e.g., "Apple" vs "Apple Inc."
        company_words = set(company_normalized.split())
        actual_words = set(actual_normalized.split())
        common_suffixes = {
            'inc', 'inc.', 'corp', 'corp.', 'ltd', 'ltd.',
            'llc', 'co', 'co.', 'corporation', 'company'
        }

        # Remove common suffixes
        company_core = company_words - common_suffixes
        actual_core = actual_words - common_suffixes

        # If core words match, consider it a match
        if company_core and actual_core:
            overlap = len(company_core & actual_core) / len(company_core)
            if overlap >= 0.7:
                return {
                    "match": True,
                    "confidence": "medium",
                    "actual_company": actual_company,
                    "suggestion": None
                }

        # No match
        return {
            "match": False,
            "confidence": "low",
            "actual_company": actual_company,
            "suggestion": (
                f"Did you mean '{actual_company}' for ticker {ticker}?"
            )
        }

    async def close(self):
        """Close the aiohttp session"""
        if self.session:
            await self.session.close()
