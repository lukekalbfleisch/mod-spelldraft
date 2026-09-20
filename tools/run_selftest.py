#!/usr/bin/env python3
"""
Read the self-test rig's verdict out of the worldserver log.

The batteries run inside Eluna (lua/SpellDraft/selftest.lua) because that is the
only layer that can see spell, talent, skill and power state. They report by
printing [SDTEST] lines, which land in the worldserver's log; this script is the
consumer that turns them back into a pass/fail verdict and an exit code.

  run_selftest.py                       verdict for the most recent run
  run_selftest.py --battery <name>      only that battery's assertions
  run_selftest.py --all-runs            every run in the window, not just the last
  run_selftest.py --file <path>         read a saved log instead of docker

Exit codes:
  0  every assertion passed
  1  at least one assertion failed
  2  no results found in the window (the rig never ran, or is disabled)

A log usually holds several runs, so by default only the LAST complete run is
scored - otherwise a fixed bug keeps being re-reported from an older run.
"""

import argparse
import re
import subprocess
import sys

WORLD_CONTAINER = "ac-worldserver"
MARKER = "[SDTEST]"

# The worldserver colourises its output, so the marker is usually preceded by an
# escape sequence and the line may carry more of them.
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[0m|\[36m|\[\?2004[hl]")

PASS, FAIL, NOTE, SECTION, SKIP = "PASS", "FAIL", "NOTE", "SECTION", "SKIP"


def read_log(args):
    if args.file:
        with open(args.file, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    try:
        result = subprocess.run(
            ["docker", "logs", WORLD_CONTAINER, "--since", f"{args.since}s"],
            capture_output=True, text=True, errors="replace", check=False,
        )
    except FileNotFoundError:
        print("docker not found on PATH", file=sys.stderr)
        raise SystemExit(2)

    if result.returncode != 0:
        print(f"could not read logs from {WORLD_CONTAINER}: {result.stderr.strip()}",
              file=sys.stderr)
        raise SystemExit(2)

    # The worldserver writes to both streams; [SDTEST] lines come through stdout
    # but joining is harmless and avoids depending on which one Eluna picked.
    return result.stdout + result.stderr


def parse(text):
    """Split the log into runs. Returns a list of {char, records, closed}."""
    runs = []
    current = None

    for raw in text.splitlines():
        if MARKER not in raw:
            continue
        line = ANSI.sub("", raw)
        payload = line.split(MARKER, 1)[1].strip()
        fields = payload.split("|")
        kind = fields[0]

        if kind == "RUN" and len(fields) > 1 and fields[1] == "start":
            meta = dict(f.split("=", 1) for f in fields[2:] if "=" in f)
            current = {"char": meta.get("char", "?"), "records": [], "closed": False}
            runs.append(current)
            continue

        if current is None:
            # Output from a run whose start scrolled out of the window.
            current = {"char": "?", "records": [], "closed": False}
            runs.append(current)

        if kind == "RUN" and len(fields) > 1 and fields[1] == "end":
            current["closed"] = True
            continue

        if kind == "SUMMARY":
            continue  # recomputed from the records themselves

        if kind in (PASS, FAIL, NOTE, SECTION, SKIP) and len(fields) >= 3:
            meta = dict(f.split("=", 1) for f in fields[3:] if "=" in f)
            current["records"].append({
                "kind": kind,
                "battery": fields[1],
                "assertion": fields[2],
                "got": meta.get("got", ""),
                "want": meta.get("want", ""),
            })

    return runs


def report(run, only_battery):
    records = [r for r in run["records"]
               if not only_battery or r["battery"] == only_battery]

    if not records:
        return None

    batteries = []
    for record in records:
        if record["battery"] not in batteries:
            batteries.append(record["battery"])

    total_pass = total_fail = 0
    print(f"character: {run['char']}"
          + ("" if run["closed"] else "   (run did not finish)"))

    for battery in batteries:
        rows = [r for r in records if r["battery"] == battery]
        passed = sum(1 for r in rows if r["kind"] == PASS)
        failed = sum(1 for r in rows if r["kind"] == FAIL)
        skipped = [r for r in rows if r["kind"] == SKIP]
        total_pass += passed
        total_fail += failed

        if skipped:
            # A skip is not a pass and not a failure - the battery declined to
            # run because the character was the wrong kind. Saying so beats
            # reporting a silent 0/0.
            reason = skipped[0]["assertion"]
            print(f"\n  [skip] {battery}  ({reason}; {skipped[0]['got']})")
            continue

        verdict = "FAIL" if failed else "ok"
        print(f"\n  [{verdict}] {battery}  ({passed} passed, {failed} failed)")

        for row in rows:
            if row["kind"] == SECTION:
                print(f"      -- {row['assertion']}")
            elif row["kind"] == FAIL:
                print(f"      FAIL  {row['assertion']}")
                print(f"            got  {row['got']}")
                print(f"            want {row['want']}")
            elif row["kind"] == NOTE:
                print(f"      note  {row['assertion']} = {row['got']}")

    print(f"\ntotal: {total_pass} passed, {total_fail} failed")
    return total_fail


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--since", type=int, default=300,
                        help="how many seconds of log to read (default 300)")
    parser.add_argument("--battery", help="only report this battery")
    parser.add_argument("--all-runs", action="store_true",
                        help="report every run in the window, not just the last")
    parser.add_argument("--file", help="read a saved log file instead of docker logs")
    args = parser.parse_args()

    runs = parse(read_log(args))
    if not runs:
        print(f"no {MARKER} results in the last {args.since}s.")
        print("is CONFIG.SELFTEST_ENABLED true, and did a battery actually run?")
        return 2

    selected = runs if args.all_runs else [runs[-1]]

    failures = 0
    reported = False
    for index, run in enumerate(selected):
        if len(selected) > 1:
            print(f"\n=== run {index + 1} of {len(selected)} ===")
        outcome = report(run, args.battery)
        if outcome is not None:
            reported = True
            failures += outcome

    if not reported:
        target = args.battery or "any battery"
        print(f"no results for {target} in the last {args.since}s.")
        return 2

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
