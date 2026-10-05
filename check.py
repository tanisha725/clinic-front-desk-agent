#!/usr/bin/env python3
"""Compare the runner's results with the `expected` block of each script.

    python3 runner.py                 # writes results/
    python3 check.py                  # checks conversations/ against results/
    python3 check.py adversarial      # checks another folder of scripts
"""

import json
import pathlib
import sys

folder = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "conversations")
results = pathlib.Path("results")
failed = 0

for path in sorted(folder.glob("*.json")):
    script = json.loads(path.read_text(encoding="utf-8"))
    expected = script["expected"]
    runs = sorted(results.glob(f"{script['id']}.run*.json"))
    if not runs:
        print(f"  MISSING {script['id']}: no result file, run runner.py first")
        failed += 1
        continue
    for run in runs:
        result = json.loads(run.read_text(encoding="utf-8"))
        called = {call["name"] for call in result["tool_calls"]}
        problems = []
        if result["terminal_state"] != expected["terminal_state"]:
            problems.append(f"terminal_state {result['terminal_state']} != {expected['terminal_state']}")
        if result["escalation_reason"] != expected["escalation_reason"]:
            problems.append(f"escalation_reason {result['escalation_reason']} != {expected['escalation_reason']}")
        for name in expected.get("must_call", []):
            if name not in called:
                problems.append(f"did not call {name}")
        for name in expected.get("must_not_call", []):
            if name in called:
                problems.append(f"called {name}")
        failed += bool(problems)
        print(f"  {'FAIL' if problems else 'pass'}  {run.name}" + "".join(f"\n          {p}" for p in problems))

all_runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(results.glob("*.json"))]
if all_runs:
    tokens = sum(r["metrics"].get("tokens", 0) for r in all_runs) / len(all_runs)
    latency = sum(r["metrics"].get("latency_ms", 0) for r in all_runs) / len(all_runs)
    print(f"\naverage per conversation over {len(all_runs)} result files: "
          f"{tokens:.0f} tokens, {latency:.0f} ms")

print(f"\n{failed} failed")
sys.exit(1 if failed else 0)
