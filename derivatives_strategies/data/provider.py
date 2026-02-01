"""
DataProvider abstract interface for market data ingestion.

All providers must implement this interface to be pluggable into the engine.
"""

from abc import ABC, abstractmethod
from typing import Optional
from derivatives_strategies.data.models import (
    Chain,
    SpotQuote,
    DividendEvent,
    RateData,
)


class DataProvider(ABC):
    """
    Abstract base class for market data providers.

    Implementations provide market data without making network calls.
    Demo and CSV providers are included; others can be added.
    """

    @abstractmethod
    def get_chain(self, symbol: str) -> Optional[Chain]:
        """
        Get option chain for a symbol.

        Args:
            symbol: Underlying symbol

        Returns:
            Option chain with spot and all available options, or None if not found
        """
        pass

    @abstractmethod
    def get_spot(self, symbol: str) -> Optional[SpotQuote]:
        """
        Get spot quote for underlying.

        Args:
            symbol: Underlying symbol

        Returns:
            Spot quote or None if not found
        """
        pass

    @abstractmethod
    def get_dividends(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> list[DividendEvent]:
        """
        Get dividend events for a symbol.

        Args:
            symbol: Underlying symbol
            start_date: Optional filter start (ISO format)
            end_date: Optional filter end (ISO format)

        Returns:
            List of dividend events within the date range
        """
        pass

    @abstractmethod
    def get_risk_free_rate(self, as_of: Optional[str] = None) -> RateData:
        """
        Get risk-free rate.

        Args:
            as_of: Optional date for historical rate

        Returns:
            Risk-free rate data
        """
        pass

    @abstractmethod
    def get_symbols(self) -> list[str]:
        """
        Get list of available symbols.

        Returns:
            List of symbol strings
        """
        pass

    @abstractmethod
    def get_as_of_date(self) -> str:
        """
        Get the as-of date for this provider's data.

        Returns:
            ISO format date string
        """
        pass

    def get_next_dividend(
        self,
        symbol: str,
        after_date: str
    ) -> Optional[DividendEvent]:
        """
        Get next dividend event after a given date.

        Args:
            symbol: Underlying symbol
            after_date: Date to search after (ISO format)

        Returns:
            Next dividend event or None
        """
        divs = self.get_dividends(symbol, start_date=after_date)
        if divs:
            return min(divs, key=lambda d: d.ex_date)
        return None

    def get_dividends_before_expiry(
        self,
        symbol: str,
        as_of: str,
        expiry: str
    ) -> list[DividendEvent]:
        """
        Get all dividends between as_of and expiry dates.

        Args:
            symbol: Underlying symbol
            as_of: Start date (ISO format)
            expiry: End date (ISO format)

        Returns:
            List of dividend events in the window
        """
        divs = self.get_dividends(symbol, start_date=as_of, end_date=expiry)
        return [d for d in divs if as_of < d.ex_date <= expiry]
