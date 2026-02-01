"""
CSV data provider for reading market data from CSV files.

Expected file formats:
- spot.csv: symbol,bid,ask,last,timestamp
- chain.csv: symbol,expiry,strike,option_type,bid,ask,last,volume,open_interest,timestamp
- dividends.csv: symbol,ex_date,amount,record_date,pay_date
- rates.csv: as_of_date,rate,tenor_days
"""

import csv
from pathlib import Path
from typing import Optional
from datetime import date, datetime

from derivatives_strategies.data.provider import DataProvider
from derivatives_strategies.data.models import (
    Chain,
    SpotQuote,
    OptionQuote,
    DividendEvent,
    RateData,
    OptionType,
)


class CSVProvider(DataProvider):
    """
    CSV-based data provider.

    Reads market data from CSV files in a specified directory.
    """

    def __init__(self, data_dir: str, as_of_date: Optional[str] = None):
        """
        Initialize CSV provider.

        Args:
            data_dir: Path to directory containing CSV files
            as_of_date: Optional as-of date override
        """
        self._data_dir = Path(data_dir)
        self._as_of = as_of_date or date.today().isoformat()

        # Load all data upfront
        self._spots: dict[str, SpotQuote] = {}
        self._chains: dict[str, Chain] = {}
        self._dividends: dict[str, list[DividendEvent]] = {}
        self._rates: list[RateData] = []

        self._load_data()

    def _load_data(self) -> None:
        """Load all CSV data files."""
        self._load_spots()
        self._load_options()
        self._load_dividends()
        self._load_rates()

    def _load_spots(self) -> None:
        """Load spot prices from spot.csv."""
        spot_file = self._data_dir / "spot.csv"
        if not spot_file.exists():
            return

        with open(spot_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["symbol"].strip().upper()
                self._spots[symbol] = SpotQuote(
                    symbol=symbol,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    last=float(row["last"]),
                    timestamp=row.get("timestamp", datetime.now().isoformat()),
                )

    def _load_options(self) -> None:
        """Load option chain from chain.csv."""
        chain_file = self._data_dir / "chain.csv"
        if not chain_file.exists():
            return

        # Group options by symbol
        options_by_symbol: dict[str, list[OptionQuote]] = {}

        with open(chain_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["symbol"].strip().upper()
                opt_type_str = row["option_type"].strip().lower()

                if opt_type_str == "call":
                    opt_type = OptionType.CALL
                elif opt_type_str == "put":
                    opt_type = OptionType.PUT
                else:
                    continue  # Skip invalid types

                option = OptionQuote(
                    symbol=symbol,
                    expiry=row["expiry"].strip(),
                    strike=float(row["strike"]),
                    option_type=opt_type,
                    bid=float(row["bid"]),
                    ask=float(row["ask"]),
                    last=float(row["last"]),
                    volume=int(row.get("volume", 0)),
                    open_interest=int(row.get("open_interest", 0)),
                    timestamp=row.get("timestamp", datetime.now().isoformat()),
                    delta=float(row["delta"]) if row.get("delta") else None,
                    gamma=float(row["gamma"]) if row.get("gamma") else None,
                    theta=float(row["theta"]) if row.get("theta") else None,
                    vega=float(row["vega"]) if row.get("vega") else None,
                    implied_vol=float(row["implied_vol"]) if row.get("implied_vol") else None,
                )

                if symbol not in options_by_symbol:
                    options_by_symbol[symbol] = []
                options_by_symbol[symbol].append(option)

        # Build chains
        for symbol, options in options_by_symbol.items():
            spot = self._spots.get(symbol)
            if spot:
                self._chains[symbol] = Chain(
                    symbol=symbol,
                    spot=spot,
                    options=options,
                    as_of=datetime.now().isoformat(),
                )

    def _load_dividends(self) -> None:
        """Load dividends from dividends.csv."""
        div_file = self._data_dir / "dividends.csv"
        if not div_file.exists():
            return

        with open(div_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                symbol = row["symbol"].strip().upper()

                div = DividendEvent(
                    symbol=symbol,
                    ex_date=row["ex_date"].strip(),
                    amount=float(row["amount"]),
                    record_date=row.get("record_date", "").strip() or None,
                    pay_date=row.get("pay_date", "").strip() or None,
                )

                if symbol not in self._dividends:
                    self._dividends[symbol] = []
                self._dividends[symbol].append(div)

        # Sort by ex_date
        for symbol in self._dividends:
            self._dividends[symbol].sort(key=lambda d: d.ex_date)

    def _load_rates(self) -> None:
        """Load risk-free rates from rates.csv."""
        rates_file = self._data_dir / "rates.csv"
        if not rates_file.exists():
            # Default rate if no file
            self._rates = [RateData(rate=0.05, as_of_date=self._as_of)]
            return

        with open(rates_file, newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rate = RateData(
                    rate=float(row["rate"]),
                    as_of_date=row["as_of_date"].strip(),
                    tenor_days=int(row["tenor_days"]) if row.get("tenor_days") else None,
                )
                self._rates.append(rate)

        self._rates.sort(key=lambda r: r.as_of_date, reverse=True)

    def get_as_of_date(self) -> str:
        return self._as_of

    def get_symbols(self) -> list[str]:
        return list(set(self._spots.keys()) | set(self._chains.keys()))

    def get_spot(self, symbol: str) -> Optional[SpotQuote]:
        return self._spots.get(symbol.upper())

    def get_chain(self, symbol: str) -> Optional[Chain]:
        return self._chains.get(symbol.upper())

    def get_dividends(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> list[DividendEvent]:
        divs = self._dividends.get(symbol.upper(), [])

        if start_date:
            divs = [d for d in divs if d.ex_date >= start_date]
        if end_date:
            divs = [d for d in divs if d.ex_date <= end_date]

        return divs

    def get_risk_free_rate(self, as_of: Optional[str] = None) -> RateData:
        target_date = as_of or self._as_of

        # Find rate for target date
        for rate in self._rates:
            if rate.as_of_date <= target_date:
                return rate

        # Default if no rates found
        if self._rates:
            return self._rates[-1]

        return RateData(rate=0.05, as_of_date=target_date)
