"""
Tests for the research MCP tool registry.
"""

from derivatives_strategies.research import registry


class TestRegistry:
    def test_has_equity_and_futures_tools(self):
        eq = registry.tools_for_asset_class(registry.EQUITY)
        fut = registry.tools_for_asset_class(registry.FUTURES)
        assert len(eq) >= 5
        assert len(fut) >= 5

    def test_market_data_quotes_present(self):
        hits = [t for t in registry.RESEARCH_TOOLS if t.tool == "get_quotes"]
        assert hits
        assert registry.EQUITY in hits[0].asset_classes
        assert registry.FUTURES in hits[0].asset_classes

    def test_categories_cover_core_research_areas(self):
        cats = set(registry.categories())
        for needed in {"quotes", "prices", "fundamentals", "positioning",
                       "commodities", "volatility", "rates"}:
            assert needed in cats

    def test_find_searches_descriptions(self):
        assert registry.find("short interest")
        assert registry.find("contango")  # in vix_term_structure description

    def test_every_tool_serializes(self):
        for t in registry.RESEARCH_TOOLS:
            d = t.to_dict()
            assert d["tool"] and d["server"] and d["asset_classes"]
