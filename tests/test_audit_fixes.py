"""
Regression tests for the 2026-07 audit fixes: policy loading, gate logic,
ledger integrity, CSV robustness, CLI provider selection, and economics
consistency. Each test class references the defect it guards against.
"""

import json
from pathlib import Path

import pytest

from derivatives_strategies.data.models import (
    ActionType,
    Chain,
    Economics,
    GateStatus,
    OptionQuote,
    OptionType,
    Position,
    Recommendation,
    SpotQuote,
    TransactionCosts,
)
from derivatives_strategies.data.csv_provider import CSVDataError, CSVProvider
from derivatives_strategies.monitoring.ledger import Ledger, create_ledger_entry
from derivatives_strategies.policy.engine import (
    Policy,
    PolicyEngine,
    PolicyOverride,
    load_policy,
)
from derivatives_strategies.policy.gates import (
    ConcentrationGate,
    DeltaGate,
    EventGate,
    GateContext,
    LiquidityGate,
    MarginGate,
    RollCreditGate,
)

EXAMPLES = Path(__file__).parent.parent / "examples"


def make_context(**kwargs) -> GateContext:
    defaults = dict(symbol="AAPL", spot=175.0, as_of="2025-01-15", rate=0.0525)
    defaults.update(kwargs)
    return GateContext(**defaults)


def make_quote(**kwargs) -> OptionQuote:
    defaults = dict(
        symbol="AAPL", expiry="2025-02-21", strike=180.0,
        option_type=OptionType.CALL, bid=2.40, ask=2.60, last=2.50,
        volume=500, open_interest=1200, timestamp="2025-01-15T15:00:00",
    )
    defaults.update(kwargs)
    return OptionQuote(**defaults)


class TestPolicyLoading:
    """The shipped example policy must load with every configured gate."""

    def test_example_policy_loads_all_gates(self):
        policy = load_policy(str(EXAMPLES / "policy.example.yml"))
        gate_names = {g.name for g in policy.gates}
        assert gate_names == {
            "LiquidityGate", "EventGate", "DividendGate", "MarginGate",
            "RollCreditGate", "ConcentrationGate", "DTEGate", "DeltaGate",
        }
        assert policy.name == "covered_call_conservative"
        assert policy.event_calendar["2025-01-28"] == ["AAPL Earnings"]
        assert policy.default_dte_max == 45
        assert policy.max_position_concentration == 0.10

    def test_gates_only_policy_is_not_a_silent_bypass(self, tmp_path):
        # Previously this loaded with zero gates configured.
        f = tmp_path / "p.yml"
        f.write_text("name: strict\ngates:\n  liquidity:\n    max_spread_pct: 0.05\n")
        policy = load_policy(str(f))
        assert len(policy.gates) == 1
        assert policy.gates[0].max_spread_pct == 0.05

    def test_unquoted_dates_in_calendar(self, tmp_path):
        f = tmp_path / "p.yml"
        f.write_text("event_calendar:\n  2025-01-28:\n    - AAPL Earnings\n")
        policy = load_policy(str(f))
        assert policy.event_calendar == {"2025-01-28": ["AAPL Earnings"]}

    def test_empty_sections_do_not_crash(self, tmp_path):
        f = tmp_path / "p.yml"
        f.write_text("name: x\ngates:\ndefaults:\noverrides:\n")
        policy = load_policy(str(f))
        assert policy.gates == []

    def test_policy_hash_changes_when_threshold_loosens(self):
        p1 = Policy(name="p", version="1", gates=[LiquidityGate(max_spread_pct=0.20)])
        p2 = Policy(name="p", version="1", gates=[LiquidityGate(max_spread_pct=0.99)])
        assert p1.policy_hash() != p2.policy_hash()


class TestOverrideHandling:
    """Overrides must respect override_allowed and expiry."""

    def _blocked_engine(self, override: PolicyOverride, override_allowed=True):
        gate = LiquidityGate(max_spread_pct=0.0001, hard=True)
        gate.override_allowed = override_allowed
        policy = Policy(name="p", version="1", gates=[gate], overrides=[override])
        return PolicyEngine(policy)

    def test_valid_override_downgrades_to_warn(self):
        engine = self._blocked_engine(PolicyOverride(
            gate_name="LiquidityGate", reason_code="APPROVED",
            authorized_by="risk", timestamp="2025-01-14T00:00:00Z",
        ))
        results = engine.evaluate(make_context(target_quote=make_quote()))
        assert results[0].status == GateStatus.WARN
        assert results[0].override_reason == "APPROVED"

    def test_expired_override_is_ignored(self):
        engine = self._blocked_engine(PolicyOverride(
            gate_name="LiquidityGate", reason_code="APPROVED",
            authorized_by="risk", timestamp="2020-01-01T00:00:00Z",
            expires="2020-01-20T00:00:00Z",
        ))
        results = engine.evaluate(make_context(target_quote=make_quote()))
        assert results[0].status == GateStatus.BLOCK

    def test_non_overridable_gate_stays_blocked(self):
        engine = self._blocked_engine(
            PolicyOverride(
                gate_name="LiquidityGate", reason_code="APPROVED",
                authorized_by="risk", timestamp="2025-01-14T00:00:00Z",
            ),
            override_allowed=False,
        )
        results = engine.evaluate(make_context(target_quote=make_quote()))
        assert results[0].status == GateStatus.BLOCK


class TestGateFixes:
    def test_margin_gate_blocks_when_exhausted(self):
        # Previously margin_available=0 was treated as "no data" and passed.
        gate = MarginGate()
        result = gate.evaluate(make_context(margin_used=500_000.0, margin_available=0.0))
        assert result.status == GateStatus.BLOCK

    def test_margin_gate_skips_when_no_data(self):
        gate = MarginGate()
        result = gate.evaluate(make_context(margin_available=None))
        assert result.status == GateStatus.PASS
        assert result.details.get("skipped") is True

    def test_roll_credit_gate_uses_real_net_credit(self):
        # Previously used spot price as "credit" and could never fire.
        gate = RollCreditGate(min_net_credit=50.0)
        blocked = gate.evaluate(make_context(
            target_quote=make_quote(), net_credit=-25.0,
        ))
        assert blocked.status == GateStatus.BLOCK
        passed = gate.evaluate(make_context(
            target_quote=make_quote(), net_credit=75.0,
        ))
        assert passed.status == GateStatus.PASS
        not_a_roll = gate.evaluate(make_context(target_quote=make_quote()))
        assert not_a_roll.status == GateStatus.PASS
        assert not_a_roll.details.get("skipped") is True

    def test_concentration_gate_scales_with_quantity(self):
        gate = ConcentrationGate(max_position_pct=0.20)
        ten_lots = Position(symbol="AAPL", quantity=-10, position_type="call",
                            strike=180.0, expiry="2025-02-21")
        result = gate.evaluate(make_context(
            portfolio_value=100_000.0, position=ten_lots,
            target_quote=make_quote(), proposed_action="open",
        ))
        # 10 contracts x $175 x 100 = $175k = 175% of portfolio
        assert result.status == GateStatus.BLOCK
        assert result.details["contracts"] == 10

    def test_concentration_gate_warns_not_blocks_on_maintenance(self):
        # Rolling an existing oversized position must not be blocked —
        # the roll does not add exposure.
        gate = ConcentrationGate(max_position_pct=0.10)
        one_lot = Position(symbol="AAPL", quantity=-1, position_type="call",
                           strike=180.0, expiry="2025-02-21")
        rolled = gate.evaluate(make_context(
            portfolio_value=100_000.0, position=one_lot,
            target_quote=make_quote(), proposed_action="roll",
        ))
        assert rolled.status == GateStatus.WARN
        opened = gate.evaluate(make_context(
            portfolio_value=100_000.0, position=one_lot,
            target_quote=make_quote(), proposed_action="open",
        ))
        assert opened.status == GateStatus.BLOCK

    def test_event_gate_ignores_other_symbols_events(self):
        gate = EventGate(blackout_days_before=2, blackout_days_after=1)
        calendar = {"2025-01-16": ["MSFT Earnings"]}
        result = gate.evaluate(make_context(
            symbol="AAPL", event_calendar=calendar,
        ))
        assert result.status == GateStatus.PASS

    def test_event_gate_blocks_own_symbol_and_macro_events(self):
        gate = EventGate(blackout_days_before=2, blackout_days_after=1)
        own = gate.evaluate(make_context(
            symbol="AAPL", event_calendar={"2025-01-16": ["AAPL Earnings"]},
        ))
        assert own.status == GateStatus.BLOCK
        macro = gate.evaluate(make_context(
            symbol="AAPL", event_calendar={"2025-01-16": ["FOMC Decision"]},
        ))
        assert macro.status == GateStatus.BLOCK

    def test_delta_gate_uses_engine_computed_delta(self):
        # Quotes without greeks previously made DeltaGate skip silently.
        gate = DeltaGate(min_delta=0.15, max_delta=0.35)
        result = gate.evaluate(make_context(
            target_quote=make_quote(delta=None), target_delta=0.60,
        ))
        assert result.status == GateStatus.WARN  # soft gate, out of range


class TestLedgerIntegrity:
    def test_chain_verifies_and_detects_tampering(self, tmp_path):
        ledger = Ledger(str(tmp_path / "ledger.jsonl"))
        for i in range(3):
            ledger.append(create_ledger_entry(
                run_id="r1", action=f"step{i}", policy_hash="ph",
                details={"i": i},
            ))
        assert ledger.verify().valid

        lines = ledger.path.read_text().splitlines()
        tampered = json.loads(lines[1])
        tampered["policy_hash"] = "EVIL"
        lines[1] = json.dumps(tampered, sort_keys=True)
        ledger.path.write_text("\n".join(lines) + "\n")
        verification = Ledger(str(ledger.path)).verify()
        assert not verification.valid
        assert verification.first_bad_seq == 2

    def test_deleted_line_detected(self, tmp_path):
        ledger = Ledger(str(tmp_path / "ledger.jsonl"))
        for i in range(3):
            ledger.append(create_ledger_entry(
                run_id="r1", action=f"step{i}", policy_hash="ph",
            ))
        lines = ledger.path.read_text().splitlines()
        del lines[1]
        ledger.path.write_text("\n".join(lines) + "\n")
        assert not Ledger(str(ledger.path)).verify().valid

    def test_chain_resumes_across_reopen(self, tmp_path):
        path = str(tmp_path / "ledger.jsonl")
        first = Ledger(path)
        first.append(create_ledger_entry(run_id="r1", action="a", policy_hash="p"))
        second = Ledger(path)
        second.append(create_ledger_entry(run_id="r2", action="b", policy_hash="p"))
        assert second.verify().valid
        entries = second.read_all()
        assert entries[1]["prev_hash"] == entries[0]["entry_hash"]

    def test_recommendation_hash_covers_approval(self):
        # Previously two recs with opposite approved flags hashed the same.
        base = dict(
            run_id="r", timestamp="t",
            position=Position(symbol="AAPL", quantity=-1, position_type="call",
                              strike=180.0, expiry="2025-02-21"),
            action=ActionType.ROLL,
        )
        approved = Recommendation(**base, approved=True)
        blocked = Recommendation(**base, approved=False, blocked_by="MarginGate")
        assert approved.inputs_hash() != blocked.inputs_hash()


class TestCSVProviderRobustness:
    def _write(self, tmp_path, name, text):
        (tmp_path / name).write_text(text)

    def test_missing_column_raises_clear_error(self, tmp_path):
        self._write(tmp_path, "spot.csv", "ticker,bid,ask,last\nAAPL,1,2,1.5\n")
        with pytest.raises(CSVDataError, match="missing required column"):
            CSVProvider(str(tmp_path))

    def test_bad_row_skipped_with_warning_good_rows_kept(self, tmp_path):
        self._write(
            tmp_path, "spot.csv",
            "symbol,bid,ask,last\nAAPL,174,175,174.5\nMSFT,N/A,410,409\n",
        )
        provider = CSVProvider(str(tmp_path), as_of_date="2025-01-15")
        assert provider.get_spot("AAPL") is not None
        assert provider.get_spot("MSFT") is None
        assert any("MSFT" in w or "line 3" in w for w in provider.load_warnings)

    def test_short_option_type_codes_accepted(self, tmp_path):
        self._write(tmp_path, "spot.csv", "symbol,bid,ask,last\nAAPL,174,175,174.5\n")
        self._write(
            tmp_path, "chain.csv",
            "symbol,expiry,strike,option_type,bid,ask,last,volume,open_interest\n"
            "AAPL,2025-02-21,180,C,2.4,2.6,2.5,,\n"
            "AAPL,2025-02-21,180,p,3.4,3.6,3.5,10,20\n",
        )
        provider = CSVProvider(str(tmp_path), as_of_date="2025-01-15")
        chain = provider.get_chain("AAPL")
        assert len(chain.options) == 2
        # Empty volume/open_interest cells default to 0 instead of crashing.
        call = chain.get_option("2025-02-21", 180.0, OptionType.CALL)
        assert call.volume == 0 and call.open_interest == 0

    def test_unknown_option_type_warns_not_silently_drops(self, tmp_path):
        self._write(tmp_path, "spot.csv", "symbol,bid,ask,last\nAAPL,174,175,174.5\n")
        self._write(
            tmp_path, "chain.csv",
            "symbol,expiry,strike,option_type,bid,ask,last\n"
            "AAPL,2025-02-21,180,CALL_OPT,2.4,2.6,2.5\n",
        )
        provider = CSVProvider(str(tmp_path), as_of_date="2025-01-15")
        assert any("unknown option_type" in w for w in provider.load_warnings)

    def test_chain_without_spot_warns(self, tmp_path):
        self._write(tmp_path, "spot.csv", "symbol,bid,ask,last\nAAPL,174,175,174.5\n")
        self._write(
            tmp_path, "chain.csv",
            "symbol,expiry,strike,option_type,bid,ask,last\n"
            "GOOG,2025-02-21,180,call,2.4,2.6,2.5\n",
        )
        provider = CSVProvider(str(tmp_path), as_of_date="2025-01-15")
        assert provider.get_chain("GOOG") is None
        assert any("no matching row in spot.csv" in w for w in provider.load_warnings)

    def test_as_of_validated(self, tmp_path):
        with pytest.raises(ValueError):
            CSVProvider(str(tmp_path), as_of_date="not-a-date")


class TestEngineIntegration:
    def test_data_dir_selects_csv_provider(self):
        # Previously --demo defaulted True and CSV was unreachable.
        from derivatives_strategies.engine.runner import Engine, EngineConfig
        config = EngineConfig(
            data_dir=str(EXAMPLES / "data"),
            use_demo_provider=False,
            as_of="2025-01-15",
            output_dir="/tmp/claude-0/-home-user-Claude/abcbbb99-2fb5-5fba-b2b8-e1ff9fcf33fc/scratchpad/test_engine_out",
            positions_path=str(EXAMPLES / "positions.example.json"),
            policy_path=str(EXAMPLES / "policy.example.yml"),
        )
        engine = Engine(config)
        assert type(engine.provider).__name__ == "CSVProvider"
        assert engine.provider.get_as_of_date() == "2025-01-15"

    def test_full_example_run_produces_valid_chained_ledger(self, tmp_path):
        from derivatives_strategies.engine.runner import Engine, EngineConfig
        config = EngineConfig(
            data_dir=str(EXAMPLES / "data"),
            use_demo_provider=False,
            as_of="2025-01-15",
            output_dir=str(tmp_path),
            positions_path=str(EXAMPLES / "positions.example.json"),
            policy_path=str(EXAMPLES / "policy.example.yml"),
        )
        result = Engine(config).run()
        assert result.positions_analyzed > 0
        ledger = Ledger(str(tmp_path / "ledger.jsonl"))
        assert ledger.verify().valid
        run_data = json.loads((tmp_path / "run.json").read_text())
        assert run_data["provider"] == "CSVProvider"
        assert run_data["as_of"] == "2025-01-15"
        assert run_data["ledger_anchor"]["head_hash"] == ledger.head_hash

    def test_close_order_limit_price_is_positive_per_share(self):
        # Previously buy_to_close orders carried negative limit prices.
        from derivatives_strategies.engine.recommender import RecommendationEngine
        from derivatives_strategies.data.demo_provider import DemoProvider
        from derivatives_strategies.policy.engine import create_default_policy

        provider = DemoProvider()
        engine = RecommendationEngine(provider, create_default_policy())
        quote = make_quote(bid=0.55, ask=0.65)
        costs = TransactionCosts(spread_cost=1, commission=0.65,
                                 exchange_fees=0.1, slippage=0.02, total=1.77)
        rec = Recommendation(
            run_id="r", timestamp="t",
            position=Position(symbol="AAPL", quantity=-2, position_type="call",
                              strike=180.0, expiry="2025-02-21"),
            action=ActionType.CLOSE,
            economics=Economics(
                gross_premium=-(0.65 * 2 * 100),  # total dollars
                transaction_costs=costs,
                net_premium=-(0.65 * 2 * 100 + 1.77),
                max_profit=0, max_loss=131.77,
            ),
            approved=True,
        )
        intents = engine.generate_order_intents([rec])
        assert len(intents) == 1
        assert intents[0].limit_price == pytest.approx(0.65)

    def test_slippage_is_per_contract(self):
        # Previously multiplied by the 100x contract multiplier.
        from derivatives_strategies.costs.model import CostModel
        model = CostModel()
        costs = model.compute_costs(make_quote(), quantity=1, is_buy=False)
        assert costs.slippage == pytest.approx(0.02 + 0.001)
