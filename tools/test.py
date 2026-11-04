"""Run the tests, each module in its own process, as many at once as there are processors. The same tests as
`python -m unittest discover -s tests -t .`, in about the time of the slowest module.

    .venv\\Scripts\\python.exe tools\\test.py                     all modules
    .venv\\Scripts\\python.exe tools\\test.py test_ui test_graph  only these

Each module is reported as it ends; the output of a module that fails follows in full.
"""

import concurrent.futures
import os
import re
import subprocess
import sys
import time

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TESTS = os.path.join(ROOT, "tests")


def run(module):
    t0 = time.monotonic()
    proc = subprocess.run([sys.executable, "-m", "unittest", "tests." + module], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    ran = re.search(r"^Ran (\d+) tests?", proc.stderr, re.M)
    return module, proc.returncode == 0, int(ran.group(1)) if ran else 0, time.monotonic() - t0, proc.stderr


def main(names):
    modules = names or [f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py")]
    for m in modules:
        if not os.path.exists(os.path.join(TESTS, m + ".py")):
            raise SystemExit("no such test module: %s" % m)
    modules.sort(key=lambda m: -os.path.getsize(os.path.join(TESTS, m + ".py")))   # the larger ones first
    t0, failed, total = time.monotonic(), [], 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        for done in concurrent.futures.as_completed([pool.submit(run, m) for m in modules]):
            module, ok, n, seconds, output = done.result()
            total += n
            print("%-4s %6.1f s  %3d  %s" % ("ok" if ok else "FAIL", seconds, n, module), flush=True)
            if not ok:
                failed.append((module, output))
    for module, output in failed:
        print("\n==== %s\n%s" % (module, output.rstrip()))
    print("\n%d tests in %d modules, %.1f s: %s" % (total, len(modules), time.monotonic() - t0,
                                                   "FAILED: " + ", ".join(m for m, _ in failed) if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
