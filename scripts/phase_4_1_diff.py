"""Phase 4.1 numerical diff: verify zero-movement of value_types tags
across all three emitters when the shared classifier replaces the inline
logic.

For each checked-in (or real-world) manifest we have:
  1. Extract the OLD value_types dicts that were emitted by the pre-4.1
     logic.
  2. Re-classify the same keys with the NEW shared function
     (ehc_contracts.metrics.build_value_types_dict).
  3. Report any disagreement.

Dashboard and ProjFin are override-only — the shared function receives
the full hand-curated dict as overrides, so the output is mechanically
identical. ReportingApp exercises the real prefix + override + default
logic against 238 totals_value_types keys + 2 fund_level_value_types
keys from a real TPG AG 3 Support Package manifest.

Produces a markdown table suitable for ehc-federation/diffs/.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

from ehc_contracts.metrics import build_value_types_dict

REPO = Path.home() / "Documents" / "GitHub"

DASH_COMPUTE = REPO / "ehc-board-dashboard" / "pipeline" / "compute.py"
PF_COMPUTE   = REPO / "ehc-board-project-financials" / "pipeline" / "compute.py"

# ReportingApp: pick the real manifest checked in at repo root for the
# 2026-04-14 cycle — 22 reports, 238 totals_value_types keys, exercises
# the prefix heuristic.
RA_MANIFEST = (
    REPO / "ehc-board-reporting-app"
    / "TPG AG 3_01_Support_Package_20260414_091418.pdf.manifest.json"
)

RA_TOTALS_OVERRIDES = {"LB_Margin": "P"}   # Only override R emits today.


def extract_module_dict(src_path: Path, var: str) -> dict:
    tree = ast.parse(src_path.read_text())
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == var
        ):
            return ast.literal_eval(node.value)
    raise KeyError(var)


def diff_python_emitter(name: str, src: Path, var: str):
    old = extract_module_dict(src, var)
    new = build_value_types_dict(old.keys(), overrides=old)
    diffs = [
        (k, old[k], new[k]) for k in old if old[k] != new[k]
    ]
    return name, len(old), diffs


def diff_reporting_app_totals(manifest_path: Path):
    data = json.loads(manifest_path.read_text())
    reports = data.get("metrics", {}).get("reports", {})
    diffs = []
    total = 0
    report_count = 0
    for rname, rdata in reports.items():
        vt = rdata.get("totals_value_types", {})
        if not vt:
            continue
        report_count += 1
        for col, old_tag in vt.items():
            total += 1
            new_tag = build_value_types_dict(
                [col], overrides=RA_TOTALS_OVERRIDES, default="INVARIANT"
            )[col]
            if old_tag != new_tag:
                diffs.append((rname, col, old_tag, new_tag))
    return report_count, total, diffs


def diff_reporting_app_fund_level(manifest_path: Path):
    """Fund-level and header value_types are hand-curated on the R
    side — the shared module's pattern rules do not apply. The
    migration does not touch these paths; we report the key count as
    part of the zero-movement narrative."""
    data = json.loads(manifest_path.read_text())
    fl = data.get("metrics", {}).get("fund_level_value_types", {})
    header_count = 0
    reports = data.get("metrics", {}).get("reports", {})
    for rdata in reports.values():
        header_count += len(rdata.get("header_value_types", {}))
    return len(fl), header_count


def main() -> int:
    lines: list[str] = []
    lines.append("# Phase 4.1 — P/F Routing migration diff report\n")
    lines.append("**Run date:** 2026-04-22")
    lines.append(
        "**V3 workbook:** 2026-04-09 Source_Data_New_V3.xlsx "
        "(no V3 read required — this migration is a pure classification "
        "rename; no numeric outputs change)"
    )
    lines.append(
        "**Branches:** phase-4.1-pf-routing on ehc-contracts, "
        "ehc-board-dashboard, ehc-board-project-financials, "
        "ehc-board-reporting-app, ehc-data-analysis, ehc-federation\n"
    )

    lines.append("## Scope")
    lines.append(
        "Phase 4.1 is a behavior-preserving migration: the three emitters "
        "still produce the same `value_types` annotations they produced "
        "before. The migration consolidates the classification rules into "
        "one shared spec (`ehc_contracts.metrics.pf_routing`) and its R "
        "twin (`ehc-board-reporting-app/Support/pf_routing.R`), both "
        "verified against the same fixture file "
        "(`ehc-contracts/tests/bmd_fixtures/pf_routing_cases.json`).\n"
    )
    lines.append(
        "Because no numeric metric is recomputed, this diff reports "
        "`value_types` tag movement, not fund/project/metric-level "
        "dollar/percentage deltas. The success criterion is **zero "
        "movement across all three emitters**.\n"
    )

    lines.append("## Dashboard — hand-curated overrides (pipeline/compute.py)\n")
    _, dash_n, dash_diffs = diff_python_emitter(
        "Dashboard", DASH_COMPUTE, "_DASHBOARD_VALUE_TYPES"
    )
    lines.append(f"- Keys classified: **{dash_n}**")
    lines.append(f"- Drift findings: **{len(dash_diffs)}**")
    if dash_diffs:
        lines.append("\n| Metric | Old | New |")
        lines.append("|---|---|---|")
        for k, o, n in dash_diffs:
            lines.append(f"| {k} | {o} | {n} |")
    lines.append("")

    lines.append("## Project Financials — hand-curated overrides (pipeline/compute.py)\n")
    _, pf_n, pf_diffs = diff_python_emitter(
        "ProjFin", PF_COMPUTE, "_PROJFIN_VALUE_TYPES"
    )
    lines.append(f"- Keys classified: **{pf_n}**")
    lines.append(f"- Drift findings: **{len(pf_diffs)}**")
    if pf_diffs:
        lines.append("\n| Metric | Old | New |")
        lines.append("|---|---|---|")
        for k, o, n in pf_diffs:
            lines.append(f"| {k} | {o} | {n} |")
    lines.append("")

    lines.append("## Reporting App — prefix heuristic + LB_Margin override\n")
    lines.append(
        "Source manifest: "
        "`TPG AG 3_01_Support_Package_20260414_091418.pdf.manifest.json` "
        "(22 reports, real production output from 2026-04-14).\n"
    )
    ra_report_count, ra_total, ra_diffs = diff_reporting_app_totals(
        RA_MANIFEST
    )
    fl_count, header_count = diff_reporting_app_fund_level(RA_MANIFEST)
    lines.append(f"- `totals_value_types` keys classified: **{ra_total}** across **{ra_report_count}** reports")
    lines.append(f"- Drift findings: **{len(ra_diffs)}**")
    lines.append(
        f"- `fund_level_value_types` keys (hand-curated, not touched by "
        f"migration): {fl_count}"
    )
    lines.append(
        f"- `header_value_types` keys (position-based, not touched by "
        f"migration): {header_count}"
    )
    if ra_diffs:
        lines.append("\n| Report | Column | Old | New |")
        lines.append("|---|---|---|---|")
        for r, c, o, n in ra_diffs:
            lines.append(f"| {r} | {c} | {o} | {n} |")
    lines.append("")

    total_keys = dash_n + pf_n + ra_total
    total_diffs = len(dash_diffs) + len(pf_diffs) + len(ra_diffs)
    lines.append("## Roll-up\n")
    lines.append("| Emitter | Keys | Drift |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Dashboard | {dash_n} | {len(dash_diffs)} |")
    lines.append(f"| Project Financials | {pf_n} | {len(pf_diffs)} |")
    lines.append(f"| Reporting App (totals) | {ra_total} | {len(ra_diffs)} |")
    lines.append(f"| **Total** | **{total_keys}** | **{total_diffs}** |")
    lines.append("")
    if total_diffs == 0:
        lines.append(
            f"**Zero movement across {total_keys} classified metrics.** "
            "Migration is behavior-preserving."
        )
    else:
        lines.append(
            f"**{total_diffs} movement(s) across {total_keys} metrics.** "
            "Investigate before merging — each drift is either a shared-"
            "function bug or a pre-existing emitter bug surfaced by the "
            "new fail-loud classifier."
        )

    lines.append("\n## Queued for follow-up (logged, not fixed in 4.1)")
    lines.append("")
    lines.append(
        "Two pre-existing emitter/auditor bugs surfaced during exploration "
        "but are scoped to later sub-phases per the federation plan's "
        '"migrate only" philosophy:'
    )
    lines.append("")
    lines.append(
        "- **4.1.1 — R-side `LB_Margin` tags INVARIANT on every non-"
        "origination_detail report.** The `derived_type_overrides = "
        "list(LB_Margin = \"P\")` in the prior code is scoped only to the "
        "totals loop; any other report containing an `LB_Margin` column "
        "inherits the default. The auditor compensates at "
        "`manifest_loader.py:345-349` (origination_detail only). "
        "Structural fix: promote `LB_Margin = \"P\"` to a global emitter "
        "default."
    )
    lines.append("")
    lines.append(
        "- **4.1.2 — Auditor silently defaults when `value_types` is "
        "missing.** `data_board_auditor/scripts/manifest_loader.py:864-"
        "866` reads `value_types.get(key)` and uses the default route "
        "when `declared_type is None`. Auditor CLAUDE.md Rule 7 says "
        '"Absent/incomplete → SKIP. Never guess." Structural fix: emit '
        "SKIP + `unaudited_reason` instead of silent default for type-"
        "dependent metrics."
    )
    lines.append("")

    out = "\n".join(lines)
    print(out)
    return 0 if total_diffs == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
