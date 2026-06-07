"""
Obsidian vault export.

Turns engine run outputs into an interlinked Obsidian vault: one note per run,
per symbol, and per recommendation, joined with ``[[wikilinks]]`` and tagged for
search. The vault ships a pre-configured ``.obsidian/`` folder with the
community **Obsidian Git** plugin enabled so the whole knowledge base can be
backed up to a remote with periodic commits.

The exporter is incremental: Symbol notes and the Dashboard accumulate links to
every run over time using managed marker blocks, so re-running the engine builds
history rather than clobbering it. Notes that are fully owned by a single run
(run notes, recommendation notes) are simply rewritten.

See https://forum.obsidian.md/t/the-easiest-way-to-setup-obsidian-git-to-backup-notes/51429
for the Obsidian Git backup workflow this layout targets.
"""

import json
import re
from pathlib import Path
from typing import Optional

from derivatives_strategies.data.models import (
    Recommendation,
    Position,
    GateStatus,
)

# Managed-block markers. Content between a matching start/end pair is owned by
# the exporter and rewritten on each run; anything outside is left untouched so
# users can annotate notes by hand.
_BLOCK_START = "<!-- ds:{name}:start -->"
_BLOCK_END = "<!-- ds:{name}:end -->"


def _slug(value: str) -> str:
    """Make a filesystem- and wikilink-safe slug."""
    value = re.sub(r"[^\w\-]+", "-", str(value).strip())
    return re.sub(r"-{2,}", "-", value).strip("-") or "untitled"


def _yaml_frontmatter(fields: dict) -> str:
    """Render a minimal YAML frontmatter block.

    Supports scalars and flat lists, which covers everything the exporter
    needs and avoids a hard dependency on a YAML serializer for output.
    """
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, bool):
            lines.append(f"{key}: {str(value).lower()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _merge_block(existing: str, name: str, links: list[str]) -> str:
    """Merge ``links`` into a named managed block within ``existing`` text.

    Existing wikilinks inside the block are preserved and de-duplicated; the
    union is written back in sorted order. If the block is absent it is created.
    """
    start = _BLOCK_START.format(name=name)
    end = _BLOCK_END.format(name=name)

    found: set[str] = set()
    pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)
    match = pattern.search(existing)
    if match:
        found.update(re.findall(r"\[\[[^\]]+\]\]", match.group(1)))
    found.update(links)

    body = "\n".join(f"- {link}" for link in sorted(found))
    block = f"{start}\n{body}\n{end}"

    if match:
        return existing[: match.start()] + block + existing[match.end():]
    sep = "" if existing.endswith("\n") or not existing else "\n\n"
    return existing + sep + block + "\n"


class ObsidianVaultExporter:
    """Writes engine run outputs into an Obsidian vault."""

    def __init__(self, vault_dir: str):
        self.vault_dir = Path(vault_dir)
        self.runs_dir = self.vault_dir / "Runs"
        self.symbols_dir = self.vault_dir / "Symbols"
        self.recs_dir = self.vault_dir / "Recommendations"

    # -- public API --------------------------------------------------------

    def export(
        self,
        run_id: str,
        timestamp: str,
        as_of: str,
        policy_name: str,
        recommendations: list[Recommendation],
        positions: list[Position],
        portfolio_value: Optional[float] = None,
    ) -> Path:
        """Export a single run into the vault, returning the run note path."""
        for directory in (self.runs_dir, self.symbols_dir, self.recs_dir):
            directory.mkdir(parents=True, exist_ok=True)

        self._ensure_obsidian_config()
        self._ensure_gitignore()

        run_slug = _slug(run_id)[:12]
        rec_links: list[str] = []
        for rec in recommendations:
            link = self._write_recommendation(run_id, run_slug, rec)
            rec_links.append(link)

        symbols = sorted({p.symbol for p in positions})
        for symbol in symbols:
            self._update_symbol(symbol, run_slug, positions, recommendations)

        run_path = self._write_run(
            run_id, run_slug, timestamp, as_of, policy_name,
            recommendations, positions, portfolio_value, rec_links, symbols,
        )
        self._update_dashboard(run_slug, timestamp, policy_name, recommendations)
        return run_path

    # -- note writers ------------------------------------------------------

    def _write_recommendation(
        self, run_id: str, run_slug: str, rec: Recommendation
    ) -> str:
        """Write a per-recommendation note and return a wikilink to it."""
        pos = rec.position
        action = rec.action.value
        note_name = _slug(f"{run_slug}-{pos.symbol}-{action}-{rec.inputs_hash()}")

        status = "blocked" if rec.blocked_by else ("approved" if rec.approved else "review")
        tags = ["recommendation", f"action/{action}", f"status/{status}", f"symbol/{_slug(pos.symbol)}"]

        frontmatter = _yaml_frontmatter({
            "type": "recommendation",
            "run": f'"[[{run_slug}]]"',
            "symbol": pos.symbol,
            "action": action,
            "approved": rec.approved,
            "blocked_by": rec.blocked_by,
            "inputs_hash": rec.inputs_hash(),
            "tags": tags,
        })

        lines = [
            frontmatter,
            "",
            f"# {pos.symbol} — {action.upper()}",
            "",
            f"Run: [[{run_slug}]] · Symbol: [[{_slug(pos.symbol)}|{pos.symbol}]]",
            "",
            self._position_block(pos),
        ]

        if rec.target_strike or rec.target_expiry or rec.target_quantity:
            target = []
            if rec.target_strike is not None:
                target.append(f"strike ${rec.target_strike:.2f}")
            if rec.target_expiry:
                target.append(f"exp {rec.target_expiry}")
            if rec.target_quantity is not None:
                target.append(f"qty {rec.target_quantity}")
            lines += ["", f"**Target:** {', '.join(target)}"]

        if rec.economics:
            lines += ["", self._economics_block(rec)]
        if rec.greeks:
            lines += ["", self._greeks_block(rec)]
        if rec.gate_results:
            lines += ["", self._gate_block(rec)]
        if rec.reason:
            lines += ["", f"**Rationale:** {rec.reason}"]
        if rec.warnings:
            lines += ["", "**Warnings:**"]
            lines += [f"- ⚠️ {w}" for w in rec.warnings]

        path = self.recs_dir / f"{note_name}.md"
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return f"[[{note_name}|{pos.symbol} {action}]]"

    def _write_run(
        self, run_id, run_slug, timestamp, as_of, policy_name,
        recommendations, positions, portfolio_value, rec_links, symbols,
    ) -> Path:
        approved = [r for r in recommendations if r.approved]
        blocked = [r for r in recommendations if r.blocked_by]
        warned = [r for r in recommendations if r.warnings]

        frontmatter = _yaml_frontmatter({
            "type": "run",
            "run_id": run_id,
            "as_of": as_of,
            "policy": policy_name,
            "timestamp": timestamp,
            "positions": len(positions),
            "approved": len(approved),
            "blocked": len(blocked),
            "tags": ["run"] + [f"symbol/{_slug(s)}" for s in symbols],
        })

        lines = [
            frontmatter,
            "",
            f"# Run {run_slug}",
            "",
            f"**As of:** {as_of} · **Policy:** {policy_name} · **Generated:** {timestamp}",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Positions analyzed | {len(positions)} |",
            f"| Recommendations | {len(recommendations)} |",
            f"| Approved | {len(approved)} |",
            f"| Blocked | {len(blocked)} |",
            f"| With warnings | {len(warned)} |",
        ]
        if portfolio_value:
            lines.append(f"| Portfolio value | ${portfolio_value:,.2f} |")

        lines += ["", "## Symbols", ""]
        lines += [f"- [[{_slug(s)}|{s}]]" for s in symbols]

        lines += ["", "## Recommendations", ""]
        lines += [f"- {link}" for link in rec_links] or ["*None.*"]

        path = self.runs_dir / f"{run_slug}.md"
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return path

    def _update_symbol(
        self, symbol, run_slug, positions, recommendations
    ) -> None:
        path = self.symbols_dir / f"{_slug(symbol)}.md"
        sym_positions = [p for p in positions if p.symbol == symbol]

        if path.exists():
            existing = path.read_text(encoding="utf-8")
        else:
            frontmatter = _yaml_frontmatter({
                "type": "symbol",
                "symbol": symbol,
                "tags": ["symbol", f"symbol/{_slug(symbol)}"],
            })
            pos_start = _BLOCK_START.format(name="positions")
            pos_end = _BLOCK_END.format(name="positions")
            runs_start = _BLOCK_START.format(name="runs")
            runs_end = _BLOCK_END.format(name="runs")
            existing = (
                f"{frontmatter}\n\n# {symbol}\n\n"
                f"Underlying tracked by the derivatives overlay engine.\n\n"
                f"## Current Positions\n\n{pos_start}\n{pos_end}\n\n"
                f"## Run History\n\n{runs_start}\n{runs_end}\n"
            )

        # Refresh the current-positions managed block with the latest snapshot.
        pos_lines = [self._position_line(p) for p in sym_positions]
        existing = self._replace_block(existing, "positions", pos_lines)

        # Accumulate run links over time.
        existing = _merge_block(existing, "runs", [f"[[{run_slug}]]"])
        path.write_text(existing, encoding="utf-8")

    def _update_dashboard(
        self, run_slug, timestamp, policy_name, recommendations
    ) -> None:
        path = self.vault_dir / "Dashboard.md"
        approved = sum(1 for r in recommendations if r.approved)
        blocked = sum(1 for r in recommendations if r.blocked_by)
        entry = (
            f"[[{run_slug}]] — {timestamp} · {policy_name} · "
            f"{approved} approved / {blocked} blocked"
        )

        if path.exists():
            existing = path.read_text(encoding="utf-8")
        else:
            frontmatter = _yaml_frontmatter({"type": "dashboard", "tags": ["dashboard"]})
            existing = (
                f"{frontmatter}\n\n# Derivatives Overlay Dashboard\n\n"
                f"Map of content for the [[Symbols]] and [[Runs]] notes produced "
                f"by the derivatives_strategies engine.\n\n"
                f"## Runs\n\n"
            )
        existing = _merge_block(existing, "dashboard-runs", [entry])
        path.write_text(existing, encoding="utf-8")

    # -- block helpers -----------------------------------------------------

    def _replace_block(self, text: str, name: str, lines: list[str]) -> str:
        start = _BLOCK_START.format(name=name)
        end = _BLOCK_END.format(name=name)
        body = "\n".join(lines) if lines else "*No open positions.*"
        block = f"{start}\n{body}\n{end}"
        pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
        if pattern.search(text):
            return pattern.sub(lambda _m: block, text)
        sep = "" if text.endswith("\n") else "\n"
        return text + sep + block + "\n"

    def _position_line(self, pos: Position) -> str:
        parts = [f"{pos.quantity} {pos.position_type}"]
        if pos.strike is not None:
            parts.append(f"@ ${pos.strike:.2f}")
        if pos.expiry:
            parts.append(f"exp {pos.expiry}")
        if pos.cost_basis is not None:
            parts.append(f"(basis ${pos.cost_basis:.2f})")
        return "- " + " ".join(parts)

    def _position_block(self, pos: Position) -> str:
        lines = ["**Current Position:**", "", self._position_line(pos)]
        return "\n".join(lines)

    def _economics_block(self, rec: Recommendation) -> str:
        eco = rec.economics
        lines = [
            "## Economics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Gross premium | ${eco.gross_premium:.2f} |",
            f"| Transaction costs | ${eco.transaction_costs.total:.2f} |",
            f"| Net premium | ${eco.net_premium:.2f} |",
            f"| Max profit | ${eco.max_profit:.2f} |",
            f"| Max loss | ${eco.max_loss:.2f} |",
        ]
        if eco.annualized_return is not None:
            lines.append(f"| Annualized return | {eco.annualized_return:.1%} |")
        return "\n".join(lines)

    def _greeks_block(self, rec: Recommendation) -> str:
        g = rec.greeks
        return "\n".join([
            "## Greeks",
            "",
            "| Greek | Value |",
            "|-------|-------|",
            f"| Delta | {g.delta:.4f} |",
            f"| Gamma | {g.gamma:.6f} |",
            f"| Theta | ${g.theta:.2f}/day |",
            f"| Vega | ${g.vega:.2f}/1% |",
        ])

    def _gate_block(self, rec: Recommendation) -> str:
        lines = ["## Gates", "", "| Gate | Status | Detail |", "|------|--------|--------|"]
        for gate in rec.gate_results:
            icon = {
                GateStatus.PASS: "✅",
                GateStatus.WARN: "⚠️",
                GateStatus.BLOCK: "⛔",
            }.get(gate.status, "")
            detail = gate.message.replace("|", "\\|")
            lines.append(f"| {gate.gate_name} | {icon} {gate.status.value} | {detail} |")
        return "\n".join(lines)

    # -- vault scaffolding -------------------------------------------------

    def _ensure_gitignore(self) -> None:
        path = self.vault_dir / ".gitignore"
        if path.exists():
            return
        path.write_text(
            "# Obsidian workspace/cache state — not worth versioning\n"
            ".obsidian/workspace.json\n"
            ".obsidian/workspace-mobile.json\n"
            ".obsidian/cache\n"
            ".trash/\n",
            encoding="utf-8",
        )

    def _ensure_obsidian_config(self) -> None:
        """Write a minimal .obsidian config with Obsidian Git enabled.

        Only created if absent, so a user's own Obsidian settings are never
        overwritten on subsequent runs.
        """
        cfg = self.vault_dir / ".obsidian"
        cfg.mkdir(parents=True, exist_ok=True)

        self._write_json_if_absent(cfg / "app.json", {
            "alwaysUpdateLinks": True,
            "newLinkFormat": "shortest",
        })
        self._write_json_if_absent(cfg / "core-plugins.json", [
            "file-explorer", "global-search", "switcher", "graph", "backlink",
            "outgoing-link", "tag-pane", "page-preview", "templates",
            "note-composer", "command-palette",
        ])
        self._write_json_if_absent(
            cfg / "community-plugins.json", ["obsidian-git"]
        )

        git_dir = cfg / "plugins" / "obsidian-git"
        git_dir.mkdir(parents=True, exist_ok=True)
        # Pre-seed Obsidian Git with periodic auto backup/pull so the vault is
        # committed and pushed without manual intervention.
        self._write_json_if_absent(git_dir / "data.json", {
            "commitMessage": "vault backup: {{date}}",
            "commitDateFormat": "YYYY-MM-DD HH:mm:ss",
            "autoSaveInterval": 10,
            "autoPushInterval": 10,
            "autoPullInterval": 10,
            "disablePush": False,
            "pullBeforePush": True,
            "syncMethod": "merge",
            "gitTimeout": 60,
        })
        self._write_json_if_absent(git_dir / "manifest.json", {
            "id": "obsidian-git",
            "name": "Git",
            "description": "Backup your vault with Git.",
        })

    @staticmethod
    def _write_json_if_absent(path: Path, payload) -> None:
        if path.exists():
            return
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def export_vault(
    vault_dir: str,
    run_id: str,
    timestamp: str,
    as_of: str,
    policy_name: str,
    recommendations: list[Recommendation],
    positions: list[Position],
    portfolio_value: Optional[float] = None,
) -> Path:
    """Convenience wrapper around :class:`ObsidianVaultExporter`."""
    exporter = ObsidianVaultExporter(vault_dir)
    return exporter.export(
        run_id=run_id,
        timestamp=timestamp,
        as_of=as_of,
        policy_name=policy_name,
        recommendations=recommendations,
        positions=positions,
        portfolio_value=portfolio_value,
    )
