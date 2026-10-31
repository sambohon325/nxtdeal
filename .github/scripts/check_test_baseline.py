#!/usr/bin/env python3
"""
Compare this run's failing tests against a committed baseline.

Why a baseline instead of "all tests must pass": DealerOS carries ~30 long-standing
count-guardrail failures. Demanding green on day one would mean disabling the gate.
Demanding "no more than N failures" is worse -- it lets a real regression slip in
whenever a stale failure gets fixed in the same PR.

So we compare the SET of failing node IDs:
  * any failure not in the baseline  -> NEW REGRESSION -> fail the build
  * any baseline failure now passing -> good news -> tell the human to shrink the baseline

Bootstrap: if the baseline file does not exist, this writes what it would have been
to the job summary and exits 0, so the first run tells you exactly what to commit.

Usage: check_test_baseline.py <pytest-output-file> <baseline-file>
"""
import os
import re
import sys

FAILED = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)")


def parse(path: str) -> set[str]:
    found: set[str] = set()
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = FAILED.match(line.strip())
            if m:
                # strip a trailing " - AssertionError: ..." if pytest glued it on
                found.add(m.group(1).split(" - ")[0].strip())
    return found


def summary(text: str) -> None:
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    out_file, baseline_file = sys.argv[1], sys.argv[2]
    current = parse(out_file)

    if not os.path.exists(baseline_file):
        summary(
            "## Test baseline not found\n\n"
            f"`{baseline_file}` does not exist yet, so this run is informational only.\n\n"
            f"Commit the following {len(current)} lines to `{baseline_file}` to arm the gate:\n\n"
            "```\n" + "\n".join(sorted(current)) + "\n```\n"
        )
        return 0

    with open(baseline_file, encoding="utf-8") as fh:
        baseline = {
            ln.strip()
            for ln in fh
            if ln.strip() and not ln.lstrip().startswith("#")
        }

    new = sorted(current - baseline)
    fixed = sorted(baseline - current)

    lines = [
        "## Test baseline check",
        "",
        f"- baseline failures: **{len(baseline)}**",
        f"- this run: **{len(current)}**",
        f"- new regressions: **{len(new)}**",
        f"- newly passing: **{len(fixed)}**",
        "",
    ]

    if fixed:
        lines += [
            "### Newly passing (remove these from the baseline)",
            "",
            "```",
            *fixed,
            "```",
            "",
        ]

    if new:
        lines += [
            "### NEW REGRESSIONS â€” these are on this change",
            "",
            "```",
            *new,
            "```",
            "",
        ]
        summary("\n".join(lines))
        return 1

    lines.append("No new regressions.")
    summary("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())