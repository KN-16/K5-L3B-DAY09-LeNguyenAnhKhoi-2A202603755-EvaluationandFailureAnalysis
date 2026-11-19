"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    def finite(value: Any) -> bool:
        if isinstance(value, bool) or value is None or isinstance(value, str):
            return True
        if isinstance(value, (int, float)):
            return math.isfinite(float(value))
        if isinstance(value, dict):
            return all(finite(v) for v in value.values())
        if isinstance(value, list):
            return all(finite(v) for v in value)
        return False

    metrics = pr.get("metrics")
    rows = pr.get("rows")
    manifest = pr.get("manifest")
    if not isinstance(metrics, dict) or not finite(metrics):
        problems.append("metrics contain NaN, infinity, or an unsupported value")
    if not isinstance(rows, list) or not isinstance(manifest, dict):
        return problems + ["report rows/manifest are missing or malformed"]

    items = manifest.get("items")
    seeds = manifest.get("seeds")
    if isinstance(items, bool) or not isinstance(items, int) or items < 1:
        problems.append("manifest.items must be a positive integer")
    if not isinstance(seeds, list) or not seeds or len(seeds) != len(set(seeds)):
        problems.append("manifest.seeds must be a non-empty unique list")
    expected_rows = items * len(seeds) if isinstance(items, int) and items >= 0 and isinstance(seeds, list) else None
    if expected_rows is not None and len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} != manifest items×seeds {expected_rows}")

    def row_keys(report_rows: list[dict]) -> list[tuple[Any, Any]]:
        return [(r.get("item_id"), r.get("seed")) for r in report_rows if isinstance(r, dict)]

    keys = row_keys(rows)
    if len(keys) != len(rows) or any(i is None or s is None for i, s in keys):
        problems.append("every row must contain item_id and seed")
    if len(keys) != len(set(keys)):
        problems.append("duplicate (item_id, seed) rows")
    base_rows = base.get("rows") or []
    base_keys = row_keys(base_rows)
    if set(keys) != set(base_keys):
        problems.append("PR (item_id, seed) set differs from baseline")
    if isinstance(seeds, list) and set(seeds) != {s for _, s in keys}:
        problems.append("manifest seed set differs from report rows")

    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures is non-empty")

    # Metrics backed by Evaluators must exist on every row. Aggregate-only metrics such as
    # pass_hat_5 and cost_per_success intentionally do not.
    from lab9.eval import aggregate
    from lab9.graders import GRADERS
    graded = [m["id"] for m in spec.get("metrics", []) if m.get("id") in GRADERS]
    for index, row in enumerate(rows):
        for mid in graded:
            if mid not in row or row[mid] is None:
                problems.append(f"row {index} has missing grader value for {mid}")
    if rows and metrics and not any("missing grader value" in p for p in problems):
        # Synthetic unit-test reports may omit cost; it is irrelevant to recomputing grader
        # aggregates and pass@k/pass^k.
        recomputed = aggregate([{**row, "cost": row.get("cost", 0.0)} for row in rows], graded,
                               k_values=spec.get("pass_k", []))
        row_backed = set(graded) | {f"{name}_{k}" for k in spec.get("pass_k", [])
                                    for name in ("pass_at", "pass_hat")}
        for mid, actual in recomputed.items():
            if mid not in row_backed:
                continue
            reported = metrics.get(mid)
            if reported is None or isinstance(reported, bool) or not isinstance(reported, (int, float)):
                problems.append(f"aggregate metric {mid} is missing or malformed")
            elif not math.isclose(float(reported), float(actual), rel_tol=0.0, abs_tol=1e-4):
                problems.append(f"aggregate metric {mid} does not match rows")

    # Slice membership is label-derived and therefore immutable in a comparison.
    def slices_by_item(report_rows: list[dict]) -> tuple[dict[str, tuple[str, ...]], bool]:
        out: dict[str, tuple[str, ...]] = {}
        consistent = True
        for row in report_rows:
            item = row.get("item_id")
            tags = tuple(sorted(row.get("slices") or []))
            if item in out and out[item] != tags:
                consistent = False
            out[item] = tags
        return out, consistent

    pr_slices, pr_consistent = slices_by_item(rows)
    base_slices, base_consistent = slices_by_item(base_rows)
    if not pr_consistent or not base_consistent:
        problems.append("slice tags are inconsistent across seeds for an item")
    if pr_slices != base_slices:
        problems.append("item slice tags differ from baseline")

    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        def by_id(entries: list[dict], field: str) -> dict[str, dict]:
            return {str(x.get(field)): x for x in entries if isinstance(x, dict) and x.get(field) is not None}

        def ratchet(current: dict, old: dict, label: str) -> None:
            if old.get("blocking") and not current.get("blocking"):
                problems.append(f"{label} changed from blocking to non-blocking")
            new_th, old_th = current.get("threshold", current), old.get("threshold", old)
            if "min" in old_th and ("min" not in new_th or new_th["min"] < old_th["min"]):
                problems.append(f"{label} minimum was loosened")
            if "max" in old_th and ("max" not in new_th or new_th["max"] > old_th["max"]):
                problems.append(f"{label} maximum was loosened")
            if "max_increase" in old_th and ("max_increase" not in new_th or
                                                new_th["max_increase"] > old_th["max_increase"]):
                problems.append(f"{label} max_increase was loosened")
            if old_th.get("no_significant_drop") and not new_th.get("no_significant_drop"):
                problems.append(f"{label} dropped no_significant_drop")

        current_metrics = by_id(spec.get("metrics", []), "id")
        for mid, old in by_id(base_spec.get("metrics", []), "id").items():
            if mid not in current_metrics:
                problems.append(f"metric {mid} disappeared from the spec")
            else:
                ratchet(current_metrics[mid], old, f"metric {mid}")
        current_slices = by_id(spec.get("slices", []), "name")
        for name, old in by_id(base_spec.get("slices", []), "name").items():
            if name not in current_slices:
                problems.append(f"slice {name} disappeared from the spec")
            else:
                ratchet(current_slices[name], old, f"slice {name}")
                if current_slices[name].get("metric") != old.get("metric"):
                    problems.append(f"slice {name} changed metric")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for rule in spec.get("slices", []):
        name, metric = rule["name"], rule["metric"]
        pid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, name), per_item(base, metric, name)
        keys = sorted(set(a) & set(b))
        verdict, note = "ok", ""
        value = sum(a.values()) / len(a) if a else None
        if not a or set(a) != set(b):
            verdict = "missing"
            note = "slice item set differs or is empty"
        elif "min" in rule and value < rule["min"]:
            verdict = "fail"
        if rule.get("no_significant_drop") and keys and set(a) == set(b):
            d, lo, hi = stats.paired_bootstrap(
                [a[k] for k in keys], [b[k] for k in keys],
                n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                confidence=bs.get("confidence", 0.95),
            )
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and rule.get("blocking"):
            blocked.append(pid)
        label = "ok" if verdict == "ok" else ("BLOCK" if rule.get("blocking") else "warn")
        threshold = {k: rule[k] for k in ("min", "no_significant_drop") if k in rule}
        shown = None if value is None else round(value, 4)
        lines.append(f"  {pid:<22} {shown!s:<8} {json.dumps(threshold):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
