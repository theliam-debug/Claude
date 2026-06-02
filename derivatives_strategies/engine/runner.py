"""
Main engine runner and CLI interface.

Orchestrates the full workflow:
1. Load policy and positions
2. Fetch market data
3. Generate recommendations
4. Evaluate gates
5. Produce outputs
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from derivatives_strategies.data.models import (
    Position,
    Recommendation,
    OrderIntent,
    LedgerEntry,
)
from derivatives_strategies.data.provider import DataProvider
from derivatives_strategies.data.demo_provider import DemoProvider
from derivatives_strategies.data.csv_provider import CSVProvider
from derivatives_strategies.policy.engine import Policy, load_policy, create_default_policy
from derivatives_strategies.engine.recommender import RecommendationEngine
from derivatives_strategies.monitoring.ledger import (
    Ledger,
    log_run_start,
    log_recommendation,
    log_run_complete,
)
from derivatives_strategies.monitoring.report import generate_risk_report
from derivatives_strategies.monitoring.obsidian import export_vault


@dataclass
class EngineConfig:
    """Configuration for the engine."""
    policy_path: Optional[str] = None
    positions_path: Optional[str] = None
    data_dir: Optional[str] = None
    output_dir: str = "./out"
    use_demo_provider: bool = True
    portfolio_value: float = 100000.0
    margin_used: float = 0.0
    margin_available: float = 50000.0
    # Optional Obsidian vault directory. When set, each run is also exported as
    # interlinked Obsidian notes for git-backed knowledge management.
    vault_dir: Optional[str] = None


@dataclass
class RunResult:
    """Result of an engine run."""
    run_id: str
    timestamp: str
    recommendations: list[Recommendation] = field(default_factory=list)
    orders: list[OrderIntent] = field(default_factory=list)
    positions_analyzed: int = 0
    approved_count: int = 0
    blocked_count: int = 0
    output_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "positions_analyzed": self.positions_analyzed,
            "recommendations_count": len(self.recommendations),
            "approved_count": self.approved_count,
            "blocked_count": self.blocked_count,
            "output_dir": self.output_dir,
        }


class Engine:
    """
    Main derivatives strategies engine.

    Orchestrates the complete workflow from data loading to output generation.
    """

    def __init__(self, config: EngineConfig):
        """
        Initialize engine.

        Args:
            config: Engine configuration
        """
        self.config = config
        self.run_id = str(uuid.uuid4())
        self.timestamp = datetime.utcnow().isoformat() + 'Z'

        # Initialize output directory
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load policy
        if config.policy_path:
            self.policy = load_policy(config.policy_path)
        else:
            self.policy = create_default_policy()

        # Initialize data provider
        if config.use_demo_provider or not config.data_dir:
            self.provider = DemoProvider()
        else:
            self.provider = CSVProvider(config.data_dir)

        # Initialize ledger
        self.ledger = Ledger(str(self.output_dir / "ledger.jsonl"))

        # Load positions
        self.positions = self._load_positions()

    def _load_positions(self) -> list[Position]:
        """Load positions from file or create demo positions."""
        if self.config.positions_path:
            return self._load_positions_from_file(self.config.positions_path)
        else:
            return self._create_demo_positions()

    def _load_positions_from_file(self, path: str) -> list[Position]:
        """Load positions from JSON file."""
        with open(path, 'r') as f:
            data = json.load(f)

        positions = []
        for pos_data in data.get('positions', data):
            pos = Position(
                symbol=pos_data['symbol'],
                quantity=pos_data['quantity'],
                position_type=pos_data['position_type'],
                strike=pos_data.get('strike'),
                expiry=pos_data.get('expiry'),
                cost_basis=pos_data.get('cost_basis'),
                open_date=pos_data.get('open_date'),
            )
            positions.append(pos)

        return positions

    def _create_demo_positions(self) -> list[Position]:
        """Create demo positions for testing."""
        # Get demo data dates
        as_of = self.provider.get_as_of_date()

        # Create sample positions
        positions = [
            # Long stock AAPL
            Position(
                symbol="AAPL",
                quantity=100,
                position_type="stock",
                cost_basis=170.00,
                open_date=as_of,
            ),
            # Short covered call AAPL
            Position(
                symbol="AAPL",
                quantity=-1,
                position_type="call",
                strike=180.0,
                expiry=self._get_demo_expiry(14),  # ~2 weeks
                cost_basis=2.50,
                open_date=as_of,
            ),
            # Long stock MSFT
            Position(
                symbol="MSFT",
                quantity=100,
                position_type="stock",
                cost_basis=370.00,
                open_date=as_of,
            ),
            # Short covered call MSFT
            Position(
                symbol="MSFT",
                quantity=-1,
                position_type="call",
                strike=385.0,
                expiry=self._get_demo_expiry(7),  # ~1 week
                cost_basis=3.00,
                open_date=as_of,
            ),
        ]

        return positions

    def _get_demo_expiry(self, days_out: int) -> str:
        """Get a demo expiry date."""
        from datetime import date, timedelta
        as_of = date.fromisoformat(self.provider.get_as_of_date())
        expiry = as_of + timedelta(days=days_out)
        # Find next Friday
        days_to_friday = (4 - expiry.weekday()) % 7
        expiry = expiry + timedelta(days=days_to_friday)
        return expiry.isoformat()

    def run(self) -> RunResult:
        """
        Execute the engine workflow.

        Returns:
            RunResult with all outputs
        """
        # Log run start
        log_run_start(
            self.ledger,
            self.run_id,
            self.policy.policy_hash(),
            len(self.positions),
            list(set(p.symbol for p in self.positions)),
        )

        # Initialize recommendation engine
        rec_engine = RecommendationEngine(
            provider=self.provider,
            policy=self.policy,
            run_id=self.run_id,
        )

        # Generate recommendations for each position
        recommendations = []
        for position in self.positions:
            rec = rec_engine.analyze_position(
                position,
                portfolio_value=self.config.portfolio_value,
                margin_used=self.config.margin_used,
                margin_available=self.config.margin_available,
            )
            recommendations.append(rec)

            # Log recommendation
            log_recommendation(
                self.ledger,
                self.run_id,
                rec,
                self.policy.policy_hash(),
            )

        # Generate order intents
        orders = rec_engine.generate_order_intents(recommendations)

        # Count results
        approved = [r for r in recommendations if r.approved]
        blocked = [r for r in recommendations if r.blocked_by]

        # Log completion
        log_run_complete(
            self.ledger,
            self.run_id,
            self.policy.policy_hash(),
            len(recommendations),
            len(approved),
            len(blocked),
        )

        # Write outputs
        self._write_outputs(recommendations, orders)

        return RunResult(
            run_id=self.run_id,
            timestamp=self.timestamp,
            recommendations=recommendations,
            orders=orders,
            positions_analyzed=len(self.positions),
            approved_count=len(approved),
            blocked_count=len(blocked),
            output_dir=str(self.output_dir),
        )

    def _write_outputs(
        self,
        recommendations: list[Recommendation],
        orders: list[OrderIntent],
    ) -> None:
        """Write all output files."""
        # run.json - Summary
        run_data = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "policy": {
                "name": self.policy.name,
                "version": self.policy.version,
                "hash": self.policy.policy_hash(),
            },
            "positions_analyzed": len(self.positions),
            "recommendations_count": len(recommendations),
            "approved_count": len([r for r in recommendations if r.approved]),
            "blocked_count": len([r for r in recommendations if r.blocked_by]),
        }
        with open(self.output_dir / "run.json", 'w') as f:
            json.dump(run_data, f, indent=2)

        # recommendations.json
        rec_data = [r.to_dict() for r in recommendations]
        with open(self.output_dir / "recommendations.json", 'w') as f:
            json.dump(rec_data, f, indent=2)

        # orders.json
        orders_data = [o.to_dict() for o in orders]
        with open(self.output_dir / "orders.json", 'w') as f:
            json.dump(orders_data, f, indent=2)

        # risk_report.md
        report = generate_risk_report(
            run_id=self.run_id,
            as_of=self.provider.get_as_of_date(),
            policy_name=self.policy.name,
            recommendations=recommendations,
            positions=self.positions,
            portfolio_value=self.config.portfolio_value,
        )
        with open(self.output_dir / "risk_report.md", 'w') as f:
            f.write(report)

        # Obsidian vault export (optional)
        if self.config.vault_dir:
            export_vault(
                vault_dir=self.config.vault_dir,
                run_id=self.run_id,
                timestamp=self.timestamp,
                as_of=self.provider.get_as_of_date(),
                policy_name=self.policy.name,
                recommendations=recommendations,
                positions=self.positions,
                portfolio_value=self.config.portfolio_value,
            )


def run_cli():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Derivatives Strategies v3 - Policy-Driven Options Overlay Toolkit"
    )
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run the engine')
    run_parser.add_argument(
        '--policy', '-p',
        help='Path to policy YAML file',
        default=None,
    )
    run_parser.add_argument(
        '--positions', '-P',
        help='Path to positions JSON file',
        default=None,
    )
    run_parser.add_argument(
        '--data', '-d',
        help='Path to data directory (for CSV provider)',
        default=None,
    )
    run_parser.add_argument(
        '--out', '-o',
        help='Output directory',
        default='./out',
    )
    run_parser.add_argument(
        '--demo',
        help='Use demo provider',
        action='store_true',
        default=True,
    )
    run_parser.add_argument(
        '--portfolio-value',
        help='Total portfolio value',
        type=float,
        default=100000.0,
    )
    run_parser.add_argument(
        '--vault',
        help='Path to an Obsidian vault directory for note export (git-backable)',
        default=None,
    )

    args = parser.parse_args()

    if args.command == 'run':
        config = EngineConfig(
            policy_path=args.policy,
            positions_path=args.positions,
            data_dir=args.data,
            output_dir=args.out,
            use_demo_provider=args.demo or not args.data,
            portfolio_value=args.portfolio_value,
            vault_dir=args.vault,
        )

        engine = Engine(config)
        result = engine.run()

        print(f"\n{'='*60}")
        print("Derivatives Strategies v3 - Run Complete")
        print(f"{'='*60}")
        print(f"Run ID: {result.run_id}")
        print(f"Positions analyzed: {result.positions_analyzed}")
        print(f"Recommendations: {len(result.recommendations)}")
        print(f"  - Approved: {result.approved_count}")
        print(f"  - Blocked: {result.blocked_count}")
        print(f"\nOutputs written to: {result.output_dir}")
        print(f"  - run.json")
        print(f"  - recommendations.json")
        print(f"  - orders.json")
        print(f"  - risk_report.md")
        print(f"  - ledger.jsonl")
        if config.vault_dir:
            print(f"\nObsidian vault updated at: {config.vault_dir}")
            print(f"  - Dashboard.md, Runs/, Symbols/, Recommendations/")
        print(f"{'='*60}\n")

    else:
        parser.print_help()


if __name__ == "__main__":
    run_cli()
