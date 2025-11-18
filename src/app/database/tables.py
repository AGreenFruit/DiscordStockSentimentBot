"""Database table abstractions for clean ORM-like operations"""
import psycopg2
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Table:
    """Base table class for database operations"""

    def __init__(self, conn, cursor, table_name: str):
        self.conn = conn
        self.cursor = cursor
        self.table_name = table_name

    def insert(
        self,
        model: BaseModel,
        on_conflict: Optional[str] = None
    ) -> bool:
        """
        Insert a Pydantic model into the table.
        """
        try:
            # Get model data as dict
            data = model.model_dump()

            # Build INSERT query
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            values = tuple(data.values())

            query = (
                f"INSERT INTO {self.table_name} ({columns}) "
                f"VALUES ({placeholders})"
            )

            if on_conflict:
                query += f" ON CONFLICT {on_conflict}"

            self.cursor.execute(query, values)
            self.conn.commit()

            return True

        except psycopg2.IntegrityError as e:
            self.conn.rollback()
            logger.debug(
                f"Integrity error inserting into {self.table_name}: {e}"
            )
            return False
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error inserting into {self.table_name}: {e}")
            raise

    def find_one(self, **conditions) -> Optional[Dict[str, Any]]:
        """
        Find a single row matching conditions.
        """
        where_clause = ' AND '.join(
            [f"{k} = %s" for k in conditions.keys()]
        )
        values = tuple(conditions.values())

        query = (
            f"SELECT * FROM {self.table_name} "
            f"WHERE {where_clause} LIMIT 1"
        )

        self.cursor.execute(query, values)
        result = self.cursor.fetchone()

        if result:
            columns = [desc[0] for desc in self.cursor.description]
            return dict(zip(columns, result))

        return None

    def find_many(self, **conditions) -> List[Dict[str, Any]]:
        """
        Find all rows matching conditions.
        """
        if conditions:
            where_clause = ' AND '.join(
                [f"{k} = %s" for k in conditions.keys()]
            )
            values = tuple(conditions.values())
            query = (
                f"SELECT * FROM {self.table_name} WHERE {where_clause}"
            )
            self.cursor.execute(query, values)
        else:
            query = f"SELECT * FROM {self.table_name}"
            self.cursor.execute(query)

        results = self.cursor.fetchall()

        if results:
            columns = [desc[0] for desc in self.cursor.description]
            return [dict(zip(columns, row)) for row in results]

        return []


class StocksTable(Table):
    """Stocks table with custom methods"""

    def __init__(self, conn, cursor):
        super().__init__(conn, cursor, "stocks")

    def upsert(self, model: BaseModel) -> bool:
        """
        Insert or update a stock's analysis results.
        """
        try:
            data = model.model_dump()

            columns = ', '.join(data.keys())
            placeholders = ', '.join(['%s'] * len(data))
            values = tuple(data.values())

            # Build update clause for all columns except ticker
            update_cols = [k for k in data.keys() if k != 'ticker']
            update_clause = ', '.join(
                [f"{col} = EXCLUDED.{col}" for col in update_cols]
            )

            query = f"""
                INSERT INTO {self.table_name} ({columns})
                VALUES ({placeholders})
                ON CONFLICT (ticker)
                DO UPDATE SET {update_clause}
            """

            self.cursor.execute(query, values)
            self.conn.commit()

            return True

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Error upserting into {self.table_name}: {e}")
            raise

    def get_stocks_needing_analysis(
        self,
        hours_threshold: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get stocks that need analysis (haven't been analyzed recently).
        Returns list of {ticker, company_name} dicts.
        """
        query = f"""
            SELECT DISTINCT s.ticker, s.company_name
            FROM {self.table_name} s
            WHERE s.last_analysis_timestamp IS NULL
               OR s.last_analysis_timestamp < NOW() - INTERVAL '{hours_threshold} hours'
        """

        self.cursor.execute(query)
        results = self.cursor.fetchall()

        if results:
            columns = [desc[0] for desc in self.cursor.description]
            return [dict(zip(columns, row)) for row in results]

        return []


class UserStockSubscriptionsTable(Table):
    """User stock subscriptions table with custom methods"""

    def __init__(self, conn, cursor):
        super().__init__(conn, cursor, "user_stock_subscriptions")

    def subscribe(
        self,
        discord_id: str,
        ticker: str,
        company_name: str
    ) -> bool:
        """
        Subscribe a user to a stock.
        Returns True if subscription was created, False if already exists.
        """
        try:
            query = f"""
                INSERT INTO {self.table_name}
                    (discord_id, ticker, company_name, subscribed_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (discord_id, ticker) DO NOTHING
                RETURNING id
            """

            self.cursor.execute(
                query,
                (discord_id, ticker, company_name, datetime.now())
            )
            result = self.cursor.fetchone()
            self.conn.commit()

            # If result is None, subscription already existed
            return result is not None

        except Exception as e:
            self.conn.rollback()
            logger.error(
                f"Error subscribing user {discord_id} to {ticker}: {e}"
            )
            raise

    def unsubscribe(self, discord_id: str, ticker: str) -> bool:
        """
        Unsubscribe a user from a stock.
        Returns True if subscription was removed, False if didn't exist.
        """
        try:
            query = f"""
                DELETE FROM {self.table_name}
                WHERE discord_id = %s AND ticker = %s
                RETURNING id
            """

            self.cursor.execute(query, (discord_id, ticker))
            result = self.cursor.fetchone()
            self.conn.commit()

            return result is not None

        except Exception as e:
            self.conn.rollback()
            logger.error(
                f"Error unsubscribing user {discord_id} from {ticker}: {e}"
            )
            raise

    def get_user_subscriptions(
        self,
        discord_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all stocks a user is subscribed to.
        """
        return self.find_many(discord_id=discord_id)

    def get_subscribers_for_ticker(self, ticker: str) -> List[str]:
        """
        Get all discord_ids subscribed to a specific ticker.
        """
        query = f"""
            SELECT discord_id
            FROM {self.table_name}
            WHERE ticker = %s
        """

        self.cursor.execute(query, (ticker,))
        results = self.cursor.fetchall()

        return [row[0] for row in results] if results else []

    def get_all_tracked_tickers(self) -> List[Dict[str, Any]]:
        """
        Get all unique tickers being tracked by any user.
        Returns list of {ticker, company_name} dicts.
        """
        query = f"""
            SELECT DISTINCT ticker, company_name
            FROM {self.table_name}
            ORDER BY ticker
        """

        self.cursor.execute(query)
        results = self.cursor.fetchall()

        if results:
            columns = [desc[0] for desc in self.cursor.description]
            return [dict(zip(columns, row)) for row in results]

        return []
