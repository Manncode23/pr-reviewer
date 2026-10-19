"""Score the reviewer against the labeled evaluation set.

Run from the project root:
    python -m eval.run_eval --max-live-calls 6

LLM responses are cached in eval/cache (keyed by prompt), so re-runs are free
and an interrupted run resumes where it stopped. Commit the cache so the
reported numbers can be reproduced without any API quota.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.agents import base
from app.agents.registry import SPECIALISTS
from app.core.config import get_settings
from app.core.llm import get_llm
from app.core.logging import setup_logging
from app.core.tracing import configure_tracing
from eval.dataset import CASES
from eval.llm_cache import CachingLLM
from eval.runner import EvalReport, evaluate
from eval.scoring import DEFAULT_TOLERANCE, summarize


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def print_report(report: EvalReport, summary: dict, caching: CachingLLM, total: int) -> None:
    print("\n" + "=" * 78)
    print(f"{'case':<26}{'expected':>9}{'found':>7}{'hit':>6}{'missed':>8}{'false+':>8}")
    print("-" * 78)
    for s in report.scores:
        print(
            f"{s.case_id:<26}{s.expected:>9}{s.findings:>7}"
            f"{s.matched_expected:>6}{len(s.missed):>8}{len(s.false_positives):>8}"
        )

    missed = [(s.case_id, label) for s in report.scores for label in s.missed]
    if missed:
        print("\nMISSED ISSUES")
        for case_id, label in missed:
            print(f"  {case_id}: {label}")

    false_positives = [(s.case_id, fp) for s in report.scores for fp in s.false_positives]
    if false_positives:
        print("\nUNMATCHED FINDINGS (counted against precision)")
        for case_id, fp in false_positives:
            print(f"  {case_id}: {fp}")

    print("\n" + "=" * 78)
    print(f"Cases scored:  {summary['cases']} of {total}")
    print(f"Recall:        {pct(summary['recall'])}  "
          f"({summary['matched_issues']}/{summary['expected_issues']} labeled issues found)")
    print(f"Precision:     {pct(summary['precision'])}  "
          f"({summary['matched_findings']}/{summary['findings']} findings matched a label)")
    print(f"F1:            {pct(summary['f1'])}")
    print(f"Clean-code false alarms (medium or worse): {summary['clean_case_false_alarms']}")
    print(f"LLM calls this run: {caching.live_calls} live, {caching.cache_hits} from cache")

    if report.pending:
        print(f"\nPENDING ({len(report.pending)}): {', '.join(report.pending)}")
        print("  Ran out of live-call budget or quota. Run again later; finished work is cached.")
    if report.errored:
        print("\nERRORED:")
        for case_id, message in report.errored.items():
            print(f"  {case_id}: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", default="security,bugs",
                        help="comma-separated specialists to evaluate")
    parser.add_argument("--max-live-calls", type=int, default=6,
                        help="most real LLM calls to make this run (cache hits are free)")
    parser.add_argument("--tolerance", type=int, default=DEFAULT_TOLERANCE,
                        help="how many lines away a finding may be and still match")
    parser.add_argument("--cases", default="", help="comma-separated case ids (default: all)")
    parser.add_argument("--cache-dir", default="eval/cache")
    parser.add_argument("--out", default="eval/results/latest.json")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    configure_tracing()

    agents = tuple(a.strip() for a in args.agents.split(",") if a.strip())
    unknown = [a for a in agents if a not in SPECIALISTS]
    if unknown:
        raise SystemExit(f"Unknown agent(s): {unknown}. Choose from {sorted(SPECIALISTS)}")

    wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
    cases = [c for c in CASES if not wanted or c.id in wanted]

    caching = CachingLLM(get_llm(), Path(args.cache_dir), settings.gemini_model, args.max_live_calls)
    base.get_llm = lambda: caching  # route every agent call through the cache

    report = evaluate(cases, agents=agents, tolerance=args.tolerance)
    summary = summarize(report.scores)
    print_report(report, summary, caching, total=len(cases))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": settings.gemini_model,
                "agents": list(agents),
                "tolerance": args.tolerance,
                "complete": not report.pending and not report.errored,
                "summary": summary,
                "cases": [asdict(s) for s in report.scores],
                "pending": report.pending,
                "errored": report.errored,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()