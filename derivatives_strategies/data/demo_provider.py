"""
Demo data provider with deterministic synthetic data.

Generates a small, reproducible option chain for 2 symbols (AAPL, MSFT)
for testing and demonstration purposes.
"""

from datetime import date, datetime, timedelta
from typing import Optional
import math

from derivatives_strategies.data.provider import DataProvider
from derivatives_strategies.data.models import (
    Chain,
    SpotQuote,
    OptionQuote,
    DividendEvent,
    RateData,
    OptionType,
)


class DemoProvider(DataProvider):
    """
    Demo provider with deterministic synthetic market data.

    Generates realistic option chains for AAPL and MSFT with:
    - Multiple expiries (weekly, monthly)
    - ATM and OTM strikes
    - Realistic bid/ask spreads
    - Scheduled dividend events
    """

    # Demo configuration - deterministic seed data
    DEMO_DATA = {
        "AAPL": {
            "spot": {"bid": 174.50, "ask": 174.55, "last": 174.52},
            "base_vol": 0.22,
            "dividend_amount": 0.24,
            "dividend_frequency_days": 91,
        },
        "MSFT": {
            "spot": {"bid": 378.00, "ask": 378.10, "last": 378.05},
            "base_vol": 0.20,
            "dividend_amount": 0.75,
            "dividend_frequency_days": 91,
        },
    }

    # Risk-free rate
    RISK_FREE_RATE = 0.0525  # 5.25% annualized

    def __init__(self, as_of_date: Optional[str] = None, seed: int = 42):
        """
        Initialize demo provider.

        Args:
            as_of_date: Valuation date (ISO format), defaults to today
            seed: Random seed for reproducibility (not used for randomness,
                  but for deterministic strike generation)
        """
        self._seed = seed
        if as_of_date:
            self._as_of = date.fromisoformat(as_of_date)
        else:
            self._as_of = date.today()
        self._timestamp = datetime.now().isoformat()

    def get_as_of_date(self) -> str:
        return self._as_of.isoformat()

    def get_symbols(self) -> list[str]:
        return list(self.DEMO_DATA.keys())

    def get_spot(self, symbol: str) -> Optional[SpotQuote]:
        if symbol not in self.DEMO_DATA:
            return None

        data = self.DEMO_DATA[symbol]["spot"]
        return SpotQuote(
            symbol=symbol,
            bid=data["bid"],
            ask=data["ask"],
            last=data["last"],
            timestamp=self._timestamp,
        )

    def get_risk_free_rate(self, as_of: Optional[str] = None) -> RateData:
        return RateData(
            rate=self.RISK_FREE_RATE,
            as_of_date=as_of or self._as_of.isoformat(),
        )

    def get_dividends(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> list[DividendEvent]:
        if symbol not in self.DEMO_DATA:
            return []

        data = self.DEMO_DATA[symbol]
        amount = data["dividend_amount"]
        freq_days = data["dividend_frequency_days"]

        # Generate quarterly dividends starting from a fixed anchor
        anchor = date(self._as_of.year, 1, 15)  # Jan 15 of current year
        dividends = []

        # Generate dividends for the year
        for i in range(4):
            ex_date = anchor + timedelta(days=i * freq_days)
            pay_date = ex_date + timedelta(days=14)

            div = DividendEvent(
                symbol=symbol,
                ex_date=ex_date.isoformat(),
                amount=amount,
                record_date=(ex_date + timedelta(days=1)).isoformat(),
                pay_date=pay_date.isoformat(),
            )
            dividends.append(div)

        # Filter by date range
        if start_date:
            dividends = [d for d in dividends if d.ex_date >= start_date]
        if end_date:
            dividends = [d for d in dividends if d.ex_date <= end_date]

        return sorted(dividends, key=lambda d: d.ex_date)

    def get_chain(self, symbol: str) -> Optional[Chain]:
        if symbol not in self.DEMO_DATA:
            return None

        spot = self.get_spot(symbol)
        if not spot:
            return None

        data = self.DEMO_DATA[symbol]
        base_vol = data["base_vol"]
        options = []

        # Generate expiries: weekly for 4 weeks, then monthly for 3 months
        expiries = self._generate_expiries()

        for expiry_date in expiries:
            expiry = expiry_date.isoformat()
            days_to_expiry = (expiry_date - self._as_of).days
            if days_to_expiry <= 0:
                continue

            # Time to expiry in years
            T = days_to_expiry / 365.0

            # Generate strikes around ATM
            strikes = self._generate_strikes(spot.mid, days_to_expiry)

            for strike in strikes:
                # Generate call and put prices using simplified Black-Scholes
                call_price, put_price = self._price_options(
                    spot.mid, strike, T, self.RISK_FREE_RATE, base_vol
                )

                # Generate realistic bid/ask spreads
                call_spread = self._calculate_spread(call_price, days_to_expiry)
                put_spread = self._calculate_spread(put_price, days_to_expiry)

                # Volume and OI based on moneyness
                moneyness = strike / spot.mid
                base_volume = max(10, int(500 * math.exp(-5 * abs(moneyness - 1))))
                base_oi = base_volume * 10

                # Call option
                if call_price > 0.05:
                    options.append(OptionQuote(
                        symbol=symbol,
                        expiry=expiry,
                        strike=strike,
                        option_type=OptionType.CALL,
                        bid=max(0.01, call_price - call_spread / 2),
                        ask=call_price + call_spread / 2,
                        last=call_price,
                        volume=base_volume,
                        open_interest=base_oi,
                        timestamp=self._timestamp,
                    ))

                # Put option
                if put_price > 0.05:
                    options.append(OptionQuote(
                        symbol=symbol,
                        expiry=expiry,
                        strike=strike,
                        option_type=OptionType.PUT,
                        bid=max(0.01, put_price - put_spread / 2),
                        ask=put_price + put_spread / 2,
                        last=put_price,
                        volume=base_volume,
                        open_interest=base_oi,
                        timestamp=self._timestamp,
                    ))

        return Chain(
            symbol=symbol,
            spot=spot,
            options=options,
            as_of=self._timestamp,
        )

    def _generate_expiries(self) -> list[date]:
        """Generate realistic option expiry dates."""
        expiries = []

        # Weekly expiries for next 4 weeks (Fridays)
        current = self._as_of
        for _ in range(4):
            # Find next Friday
            days_until_friday = (4 - current.weekday()) % 7
            if days_until_friday == 0 and current == self._as_of:
                days_until_friday = 7
            next_friday = current + timedelta(days=days_until_friday)
            expiries.append(next_friday)
            current = next_friday + timedelta(days=1)

        # Monthly expiries (3rd Friday of each month) for next 3 months
        for month_offset in range(1, 4):
            year = self._as_of.year
            month = self._as_of.month + month_offset
            if month > 12:
                month -= 12
                year += 1

            # Find 3rd Friday
            first_day = date(year, month, 1)
            first_friday = first_day + timedelta(days=(4 - first_day.weekday()) % 7)
            third_friday = first_friday + timedelta(days=14)
            if third_friday not in expiries:
                expiries.append(third_friday)

        return sorted(expiries)

    def _generate_strikes(self, spot: float, days_to_expiry: int) -> list[float]:
        """Generate strike prices around ATM."""
        # Determine strike increment based on price level
        if spot < 50:
            increment = 2.5
        elif spot < 200:
            increment = 5.0
        else:
            increment = 10.0

        # Round spot to nearest increment
        atm_strike = round(spot / increment) * increment

        # Generate strikes: more for longer-dated options
        if days_to_expiry < 14:
            num_strikes = 5
        elif days_to_expiry < 45:
            num_strikes = 7
        else:
            num_strikes = 9

        strikes = []
        for i in range(-num_strikes // 2, num_strikes // 2 + 1):
            strike = atm_strike + i * increment
            if strike > 0:
                strikes.append(strike)

        return strikes

    def _price_options(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float
    ) -> tuple[float, float]:
        """
        Price call and put using Black-Scholes formula.

        Returns:
            Tuple of (call_price, put_price)
        """
        if T <= 0:
            # At expiry
            call = max(0, S - K)
            put = max(0, K - S)
            return call, put

        # Black-Scholes
        d1 = (math.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        # Standard normal CDF approximation
        def norm_cdf(x: float) -> float:
            return (1 + math.erf(x / math.sqrt(2))) / 2

        call = S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
        put = K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)

        return max(0.01, call), max(0.01, put)

    def _calculate_spread(self, price: float, days_to_expiry: int) -> float:
        """Calculate realistic bid-ask spread."""
        # Base spread as percentage of price
        if price < 0.50:
            spread_pct = 0.20  # 20% for very cheap options
        elif price < 2.0:
            spread_pct = 0.10  # 10%
        elif price < 10.0:
            spread_pct = 0.05  # 5%
        else:
            spread_pct = 0.02  # 2%

        # Tighter spreads for shorter-dated options
        if days_to_expiry < 7:
            spread_pct *= 0.8
        elif days_to_expiry > 60:
            spread_pct *= 1.2

        # Minimum spread
        spread = max(0.02, price * spread_pct)

        # Round to penny
        return round(spread * 100) / 100
