"""Single entry point for the pipeline. Today only the collection stage and the catalogue tools exist.

    python run.py collect                       # every enabled collector
    python run.py collect --sources wikipedia,frankfurter --since 2026-01-01
    python run.py collect --dry-run             # print what would be requested; no network, no files written
    python run.py list                          # sources, implementation status, enabled/gated state
    python run.py catalogue build|validate      # regenerate / check config/products.csv from config/model_specs.yaml

Collection is on demand only (no scheduler). Parse/clean/build steps are not implemented yet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "code"))  # no install needed: code/ holds the packages

from scraping import __version__, catalogue, settings, timeutil  # noqa: E402
from scraping.base import (SOURCES_PATH, IncompleteCollector, RunContext, SourceConfig, Summary,  # noqa: E402
                           load_sources)
from scraping.registry import REGISTRY  # noqa: E402


def gate(cfg: SourceConfig) -> str:
    """Reason a source must not run, or ''. Scraped sites need an explicit terms check (plan: Limitations)."""
    if not cfg.enabled:
        return "disabled in config/sources.yaml (set enabled: true)"
    if cfg.kind in {"retail", "scrape"} and not cfg.terms_checked:
        return "robots.txt/terms not yet reviewed (set terms_checked: true in config/sources.yaml after review)"
    return ""


def select(names: list[str] | None, sources: dict[str, SourceConfig]) -> list[str]:
    if not names:
        return [n for n in REGISTRY if n in sources]
    unknown = [n for n in names if n not in REGISTRY or n not in sources]
    if unknown:
        raise SystemExit(f"unknown source(s): {', '.join(unknown)}; available: {', '.join(REGISTRY)}")
    return names


def run_collect(names: list[str], ctx: RunContext, sources: dict[str, SourceConfig]) -> list[Summary]:
    started = ctx.now()
    summaries: list[Summary] = []
    for name in names:
        cfg = sources[name]
        reason = gate(cfg)
        if reason:
            summaries.append(Summary(name, "skipped", note=reason))
            continue
        collector = REGISTRY[name](cfg, ctx)
        if ctx.dry_run:
            targets = collector.plan()
            summaries.append(Summary(name, "dry-run", planned=len(targets), note=collector.implementation))
            for t in targets:
                print(f"  [{name}] {t.url} {t.safe_params() or ''}")
            continue
        try:
            summaries.append(collector.collect())
        except IncompleteCollector as exc:
            summaries.append(Summary(name, "incomplete", note=str(exc)))
        except Exception as exc:  # noqa: BLE001 - one broken source must not stop the others
            summaries.append(Summary(name, "failed", note=repr(exc)))

    if not ctx.dry_run:
        runs = ctx.meta_dir / "runs.jsonl"
        prev = None
        if runs.exists():
            lines = runs.read_text(encoding="utf-8").strip().splitlines()
            prev = json.loads(lines[-1])["started_utc"] if lines else None
        days_since = None
        if prev:
            days_since = (started - datetime.strptime(prev, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).days
        ctx.append_jsonl("runs.jsonl", {
            "run_id": ctx.run_id, "started_utc": timeutil.iso_utc(started), "ended_utc": timeutil.iso_utc(ctx.now()),
            "code_version": __version__, "sources_config_sha256": hashlib.sha256(
                SOURCES_PATH.read_bytes()).hexdigest()[:16],
            "since": ctx.since, "days_since_previous_run": days_since,
            "summaries": [s.as_dict() for s in summaries]})
    return summaries


def print_summaries(summaries: list[Summary]) -> None:
    print(f"{'source':18s} {'status':11s} planned fetched up-to-date failed  note")
    for s in summaries:
        print(f"{s.source:18s} {s.status:11s} {s.planned:7d} {s.fetched:7d} {s.skipped_up_to_date:10d} "
              f"{s.failed:6d}  {s.note}")


def cmd_list(sources: dict[str, SourceConfig]) -> None:
    print(f"{'source':18s} {'kind':7s} {'implementation':22s} {'gate'}")
    for name, cls in REGISTRY.items():
        cfg = sources.get(name)
        state = "NOT IN CONFIG" if cfg is None else (gate(cfg) or "ready")
        print(f"{name:18s} {cfg.kind if cfg else '-':7s} {cls.implementation:22s} {state}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show sources and their status")
    c = sub.add_parser("collect", help="run collectors on demand")
    c.add_argument("--sources", help="comma-separated source names (default: all)")
    c.add_argument("--since", help="ISO date; start of the window for archive-style sources")
    c.add_argument("--dry-run", action="store_true", help="print planned requests only")
    k = sub.add_parser("catalogue", help="build or validate config/products.csv")
    k.add_argument("action", choices=["build", "validate"])
    args = parser.parse_args(argv)

    if args.command == "catalogue":
        return catalogue.main([args.action])

    sources = load_sources()
    if args.command == "list":
        cmd_list(sources)
        return 0

    names = select([n for n in (args.sources or "").split(",") if n], sources)
    ctx = RunContext(data_dir=settings.data_dir(), dry_run=args.dry_run, since=args.since)
    summaries = run_collect(names, ctx, sources)
    print_summaries(summaries)
    return 1 if any(s.status == "failed" for s in summaries) else 0


if __name__ == "__main__":
    sys.exit(main())
