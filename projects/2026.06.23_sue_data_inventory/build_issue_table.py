"""
Turn the per-asset blocker enumeration (out/upgrade_results.json, produced by
run_issue12.py) into a one-row-per-issue table.

An asset with multiple independent blockers gets one row per blocker, so the
same asset_number appears multiple times with issue_number 1..N. An asset that
now upgrades cleanly gets a single row saying so.

  uv run python build_issue_table.py
"""

import json
import re
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent
RESULTS = SCRIPT_DIR / "out" / "upgrade_results.json"
OUT_CSV = SCRIPT_DIR / "issue12_upgrade_failures.csv"
OUT_MD = SCRIPT_DIR / "issue12_upgrade_failures.md"

PYDANTIC_MSG = re.compile(r"^\s{2,}(?P<msg>.+?)\s+\[type=(?P<type>[a-zA-Z0-9_.]+)", re.M)


def parse_error(field, error_full):
    """Return (what_is_wrong, proposed_solution) for one blocker."""
    # Custom funder error, e.g. "Unsupported funder type: NINMH"
    m = re.search(r"Unsupported funder type:\s*(?P<funder>.+)", error_full)
    if m:
        funder = m.group("funder").strip()
        hint = " (likely a typo for NIMH)" if funder.upper() in {"NINMH", "NIMH"} else ""
        return (
            f"data_description: funding_source has an unsupported funder '{funder}'{hint} "
            f"— stored as a bare string instead of a structured funder",
            f"Replace the '{funder}' funder string with a proper structured funder record, then re-run the upgrader",
        )

    # Pydantic validation error: pull the field location + message
    loc, msg, etype = "", "", ""
    last_loc = ""
    for line in error_full.splitlines():
        if not line.strip():
            continue
        mm = PYDANTIC_MSG.match(line)
        if mm:
            msg, etype = mm.group("msg").strip(), mm.group("type")
            loc = last_loc
            break
        if not line.startswith(" ") and "validation error" not in line and ":" not in line[:3]:
            last_loc = line.strip()

    loc = loc or "(field)"
    loc = re.sub(r"\.dt$", "", loc)  # pydantic's AwareDatetime wrapper -> the real field
    null_input = "input_value=None" in error_full

    if etype == "datetime_type" or ("datetime" in msg and "start_date_time" in loc):
        return (
            f"{field}: '{loc}' is {'null' if null_input else 'invalid'} — a valid datetime is required",
            f"Backfill {field}.{loc} with a valid datetime, then re-run the upgrader",
        )
    if etype == "string_type" and "subject_id" in loc:
        return (
            f"{field}: '{loc}' is null — a string is required",
            f"Populate {field}.subject_id (use the asset's subject id), then re-run the upgrader",
        )
    if etype == "date_type" or ("date" in msg and "start_date" in loc):
        return (
            f"{field}: '{loc}' is {'null' if null_input else 'invalid'} — a valid date is required",
            f"Backfill {field}.{loc} with a valid date, then re-run the upgrader",
        )
    # generic pydantic fallback
    return (
        f"{field}: '{loc}' {msg.lower()}" if msg else f"{field}: {error_full.splitlines()[0][:120]}",
        f"Correct {field}.{loc} in the v1 metadata, then re-run the upgrader",
    )


def main():
    results = json.loads(RESULTS.read_text())

    rows = []
    asset_number = 0
    for name, res in results.items():
        asset_number += 1

        if not res.get("found"):
            issues = [("(asset)", "Asset not found in the v1 DocDB", "Locate the asset / source metadata")]
        elif res.get("upgrades_fine"):
            issues = [("(none)", "Upgrades fine with the current upgrader", "Re-run upgrader on asset (no metadata fix needed)")]
        else:
            issues = []
            for b in res.get("blockers", []):
                what, fix = parse_error(b["field"], b.get("error_full", b.get("error_first_line", "")))
                issues.append((b["field"], what, fix))
            if res.get("stuck") and not issues:
                issues = [("(asset)", f"Upgrade failed: {res['stuck']}", "Investigate manually")]

        for issue_number, (field, what, fix) in enumerate(issues, 1):
            rows.append({
                "asset_number": asset_number,
                "issue_number": issue_number,
                "name": name,
                "field": field,
                "what_is_wrong": what,
                "proposed_solution": fix,
            })

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)

    # markdown table (column order per request)
    md = ["| asset_number | issue_number | name | field | what_is_wrong | proposed_solution |",
          "|---|---|---|---|---|---|"]
    for r in df.itertuples(index=False):
        md.append(
            f"| {r.asset_number} | {r.issue_number} | `{r.name}` | {r.field} | "
            f"{r.what_is_wrong} | {r.proposed_solution} |"
        )
    OUT_MD.write_text("\n".join(md) + "\n")

    # console summary
    n_assets = df["asset_number"].nunique()
    multi = df.groupby("asset_number").size()
    print(f"{len(df)} issues across {n_assets} assets "
          f"({(multi > 1).sum()} assets have >1 issue, "
          f"{(df['what_is_wrong'].str.startswith('Upgrades fine')).sum()} upgrade fine).")
    print("\nIssues by field:")
    print(df.groupby("field").size().to_string())
    print(f"\nWrote {OUT_CSV}")
    print(f"Wrote {OUT_MD}")


if __name__ == "__main__":
    main()
