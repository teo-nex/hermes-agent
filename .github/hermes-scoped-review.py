import json
import os
from pathlib import Path
import re
import subprocess

review = json.loads(Path(".github/hermes-scoped-review.json").read_text())

def run(label, paths):
    path = Path(os.environ["RUNNER_TEMP"]) / (label + ".log")
    with path.open("w") as log:
        result = subprocess.run(["scripts/run_tests.sh", "-j", "2", "--file-retries", "0", *paths], stdout=log, stderr=subprocess.STDOUT)
    output = path.read_text()
    print(label, "exit", result.returncode, flush=True)
    for line in output.splitlines():
        if "=== Summary:" in line:
            print(line, flush=True)
    return result.returncode, output

code, output = run("fixed", review["suites"])
if code or "NO TESTS RAN" in output:
    print(output[-24000:])
    raise SystemExit(1)
for source in review["sources"]:
    Path(source).write_bytes(subprocess.check_output(["git", "show", review["base"] + ":" + source]))
code, output = run("baseline", review["regressions"])
missing = [path for path in review["regressions"] if "FAILED " + path + "::" not in output]
if not code or missing or any(marker in output for marker in ("NO TESTS RAN", "runner crashed:", "ERROR collecting")):
    print("Missing expected failing regressions:", missing)
    print(output[-24000:])
    raise SystemExit(1)
for line in output.splitlines():
    if line.startswith("FAILED tests/"):
        print(line)
print("All selected fixes pass; each regression file fails against the unchanged base.", flush=True)
