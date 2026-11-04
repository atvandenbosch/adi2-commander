"""Run the tests spread over as many processes as there are processors: the same tests as
`python -m unittest discover -s tests -t .`. They are dealt out by how long each took the last time (kept in
build\\test-times.json), the longest first; a class with a setUpClass of its own stays in one process.

    .venv\\Scripts\\python.exe tools\\test.py                     all modules
    .venv\\Scripts\\python.exe tools\\test.py test_ui test_graph  only these

Reported per module at the end, with the time its tests took together; the output of a process with a failing test
follows in full.
"""

import concurrent.futures
import json
import os
import subprocess
import sys
import time
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TESTS = os.path.join(ROOT, "tests")
TIMES = os.path.join(ROOT, "build", "test-times.json")


def flatten(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from flatten(t)
        else:
            yield t


def list_tests(modules):
    """In a process of its own: one line per test, its id and whether its class has its own setUpClass."""
    loader = unittest.TestLoader()
    for m in modules:
        for t in flatten(loader.loadTestsFromName("tests." + m)):
            own = type(t).setUpClass.__func__ is not unittest.TestCase.setUpClass.__func__
            print("%s\t%d" % (t.id(), own))


class Timed(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.times = {}

    def addDuration(self, test, elapsed):
        self.times[test.id()] = self.times.get(test.id(), 0.0) + elapsed


def run_tests(ids):
    """In a process of its own: run these tests; the report on stderr, the times and failures as JSON on stdout."""
    suite = unittest.TestLoader().loadTestsFromNames(ids)
    result = unittest.TextTestRunner(stream=sys.stderr, resultclass=Timed, verbosity=1).run(suite)
    failed = [t.id() for t, _ in result.failures + result.errors] + [t.id() for t in result.unexpectedSuccesses]
    print(json.dumps({"times": result.times, "failed": failed, "ran": result.testsRun}))


def worker(ids):
    env = dict(os.environ, OPENBLAS_NUM_THREADS="1")  # the processes share the cores; numpy's own threads would not
    proc = subprocess.run([sys.executable, __file__, "--run", *ids], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    try:
        report = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):                  # the process died: all of its tests count as failed
        report = {"times": {}, "failed": list(ids), "ran": 0}
    return ids, report, proc.stderr


def deal(units, times, n):
    """Units (lists of ids) over n processes, the longest first, each to the one with the least so far."""
    known = sorted(times.values())
    default = known[len(known) // 2] if known else 1.0
    cost = lambda unit: sum(times.get(i, default) for i in unit)        # noqa: E731
    bins = [[0.0, []] for _ in range(n)]
    for unit in sorted(units, key=cost, reverse=True):
        b = min(bins, key=lambda b: b[0])
        b[0] += cost(unit)
        b[1].extend(unit)
    return [ids for _, ids in bins if ids]


def main(names):
    modules = names or sorted(f[:-3] for f in os.listdir(TESTS) if f.startswith("test_") and f.endswith(".py"))
    for m in modules:
        if not os.path.exists(os.path.join(TESTS, m + ".py")):
            raise SystemExit("no such test module: %s" % m)
    t0 = time.monotonic()
    listing = subprocess.run([sys.executable, __file__, "--list", *modules], cwd=ROOT, capture_output=True,
                             text=True, encoding="utf-8", errors="replace")
    if listing.returncode != 0:
        raise SystemExit("could not list the tests:\n" + listing.stderr)
    units, together = [], {}
    for line in listing.stdout.splitlines():
        test, own = line.rsplit("\t", 1)
        if own == "1":                                # a setUpClass of its own: the class in one process
            together.setdefault(test.rsplit(".", 1)[0], []).append(test)
        else:
            units.append([test])
    units += together.values()
    try:
        with open(TIMES, encoding="utf-8") as f:
            times = json.load(f)
    except (OSError, ValueError):
        times = {}

    per_module, outputs, failed = {}, [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=os.cpu_count() or 1) as pool:
        jobs = [pool.submit(worker, ids) for ids in deal(units, times, os.cpu_count() or 1)]
        for job in concurrent.futures.as_completed(jobs):
            ids, report, output = job.result()
            times.update(report["times"])
            failed += report["failed"]
            if report["failed"]:
                outputs.append(output)
            for test in ids:
                m = test.split(".")[1]
                n, seconds, bad = per_module.get(m, (0, 0.0, 0))
                per_module[m] = (n + 1, seconds + report["times"].get(test, 0.0), bad + (test in report["failed"]))

    for m, (n, seconds, bad) in sorted(per_module.items(), key=lambda kv: -kv[1][1]):
        print("%-4s %6.1f s  %3d  %s" % ("FAIL" if bad else "ok", seconds, n, m))
    for output in outputs:
        print("\n" + output.rstrip())
    os.makedirs(os.path.dirname(TIMES), exist_ok=True)
    with open(TIMES, "w", encoding="utf-8") as f:
        json.dump(times, f, indent=0, sort_keys=True)
    bad_modules = sorted({t.split(".")[1] for t in failed})
    print("\n%d tests in %d modules, %.1f s: %s" % (sum(n for n, _, _ in per_module.values()), len(per_module),
                                                   time.monotonic() - t0,
                                                   "FAILED: " + ", ".join(bad_modules) if failed else "OK"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, ROOT)                          # as `python -m unittest` from the root: tests is a package
    if sys.argv[1:2] == ["--list"]:
        list_tests(sys.argv[2:])
    elif sys.argv[1:2] == ["--run"]:
        run_tests(sys.argv[2:])
    else:
        sys.exit(main(sys.argv[1:]))
