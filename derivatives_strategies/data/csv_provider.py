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


class CSVDataError(ValueError):
    """Raised when a CSV file is structurally unusable (missing columns)."""


def _require_columns(reader: csv.DictReader, required: list, filename: str) -> None:
    fields = set(reader.fieldnames or [])
    missing = [c for c in required if c not in fields]
    if missing:
        raise CSVDataError(
            f"{filename}: missing required column(s) {missing}; "
            f"found {sorted(fields)}"
        )


def _parse_float(row: dict, key: str, filename: str, line: int) -> float:
    raw = (row.get(key) or "").strip()
    try:
        return float(raw)
    except ValueError:
        raise ValueError(
            f"{filename} line {line}: column '{key}' has non-numeric value '{raw}'"
        )


def _parse_int_or_default(row: dict, key: str, default: int = 0) -> int:
    """Absent columns and empty cells both fall back to the default."""
    raw = (row.get(key) or "").strip()
    if not raw:
        return default
    return int(float(raw))


def _parse_optional_float(row: dict, key: str) -> Optional[float]:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    return float(raw)


class CSVProvider(DataProvider):
    """
    CSV-based data provider.

    Reads market data from CSV files in a specified directory. Structural
    problems (missing columns) raise immediately; bad rows are skipped and
    collected in load_warnings so callers can surface them rather than
    silently losing data.
    """

    def __init__(self, data_dir: str, as_of_date: Optional[str] = None):
        """
        Initialize CSV provider.

        Args:
            data_dir: Path to directory containing CSV files
            as_of_date: Optional as-of date override (YYYY-MM-DD). Defaults
                to today — pass explicitly when analyzing historical data.
        """
        self._data_dir = Path(data_dir)
        self._as_of = as_of_date or date.today().isoformat()
        # Validate format early so a bad date fails loudly here.
        date.fromisoformat(self._as_of)

        # Load all data upfront
        self._spots: dict[str, SpotQuote] = {}
        self._chains: dict[str, Chain] = {}
        self._dividends: dict[str, list[DividendEvent]] = {}
        self._rates: list[RateData] = []
        self.load_warnings: list[str] = []

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
            _require_columns(reader, ["symbol", "bid", "ask", "last"], "spot.csv")
            for line, row in enumerate(reader, start=2):
                try:
                    symbol = row["symbol"].strip().upper()
                    if not symbol:
                        raise ValueError(f"spot.csv line {line}: empty symbol")
                    self._spots[symbol] = SpotQuote(
                        symbol=symbol,
                        bid=_parse_float(row, "bid", "spot.csv", line),
                        ask=_parse_float(row, "ask", "spot.csv", line),
                        last=_parse_float(row, "last", "spot.csv", line),
                        timestamp=(row.get("timestamp") or "").strip()
                        or datetime.now().isoformat(),
                    )
                except ValueError as exc:
                    self.load_warnings.append(str(exc))

    def _load_options(self) -> None:
        """Load option chain from chain.csv."""
        chain_file = self._data_dir / "chain.csv"
        if not chain_file.exists():
            return

        # Group options by symbol
        options_by_symbol: dict[str, list[OptionQuote]] = {}

        with open(chain_file, newline='') as f:
            reader = csv.DictReader(f)
            _require_columns(
                reader,
                ["symbol", "expiry", "strike", "option_type", "bid", "ask", "last"],
                "chain.csv",
            )
            for line, row in enumerate(reader, start=2):
                try:
                    symbol = row["symbol"].strip().upper()
                    opt_type_str = row["option_type"].strip().lower()

                    if opt_type_str in ("call", "c"):
                        opt_type = OptionType.CALL
                    elif opt_type_str in ("put", "p"):
                        opt_type = OptionType.PUT
                    else:
                        raise ValueError(
                            f"chain.csv line {line}: unknown option_type "
                            f"'{row['option_type']}' (expected call/put)"
                        )

                    option = OptionQuote(
                        symbol=symbol,
                        expiry=row["expiry"].strip(),
                        strike=_parse_float(row, "strike", "chain.csv", line),
                        option_type=opt_type,
                        bid=_parse_float(row, "bid", "chain.csv", line),
                        ask=_parse_float(row, "ask", "chain.csv", line),
                        last=_parse_float(row, "last", "chain.csv", line),
                        volume=_parse_int_or_default(row, "volume"),
                        open_interest=_parse_int_or_default(row, "open_interest"),
                        timestamp=(row.get("timestamp") or "").strip()
                        or datetime.now().isoformat(),
                        delta=_parse_optional_float(row, "delta"),
                        gamma=_parse_optional_float(row, "gamma"),
                        theta=_parse_optional_float(row, "theta"),
                        vega=_parse_optional_float(row, "vega"),
                        implied_vol=_parse_optional_float(row, "implied_vol"),
                    )
                except ValueError as exc:
                    self.load_warnings.append(str(exc))
                    continue

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
                    as_of=self._as_of,
                )
            else:
                self.load_warnings.append(
                    f"chain.csv: {len(options)} option(s) for '{symbol}' "
                    "dropped — no matching row in spot.csv"
                )

    def _load_dividends(self) -> None:
        """Load dividends from dividends.csv."""
        div_file = self._data_dir / "dividends.csv"
        if not div_file.exists():
            return

        with open(div_file, newline='') as f:
            reader = csv.DictReader(f)
            _require_columns(reader, ["symbol", "ex_date", "amount"], "dividends.csv")
            for line, row in enumerate(reader, start=2):
                try:
                    symbol = row["symbol"].strip().upper()
                    div = DividendEvent(
                        symbol=symbol,
                        ex_date=row["ex_date"].strip(),
                        amount=_parse_float(row, "amount", "dividends.csv", line),
                        record_date=(row.get("record_date") or "").strip() or None,
                        pay_date=(row.get("pay_date") or "").strip() or None,
                    )
                except ValueError as exc:
                    self.load_warnings.append(str(exc))
                    continue

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
            _require_columns(reader, ["as_of_date", "rate"], "rates.csv")
            for line, row in enumerate(reader, start=2):
                try:
                    rate = RateData(
                        rate=_parse_float(row, "rate", "rates.csv", line),
                        as_of_date=row["as_of_date"].strip(),
                        tenor_days=(
                            _parse_int_or_default(row, "tenor_days", default=0) or None
                        ),
                    )
                except ValueError as exc:
                    self.load_warnings.append(str(exc))
                    continue
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
