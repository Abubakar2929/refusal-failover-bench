"""Entry point: python run.py --exp A|B|C|D [...] or python run.py --selftest. Only dispatches; logic lives in each role's folder."""
import argparse
import importlib
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SELFTEST_PACKAGES = ["contracts", "mock_provider", "agent_exp", "analysis", "routers", "live", "data", "defences"]
EXP_MODULES = {"A": "routers.runner", "B": "live.runner", "C": "agent_exp.runner", "D": "defences.runner"}


def run_selftests() -> int:
    failures = []
    for pkg in SELFTEST_PACKAGES:
        if subprocess.run([sys.executable, "-m", f"{pkg}.selftest"], cwd=ROOT).returncode != 0:
            failures.append(pkg)
    if failures:
        print("SELFTEST: FAILED: " + ", ".join(failures))
        return 1
    print("SELFTEST: ALL PASSED")
    return 0


def run_experiment(args: argparse.Namespace) -> None:
    module_name = EXP_MODULES[args.exp]
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name != module_name:
            raise
        sys.exit(f"{module_name} not written yet (see PLAN.md section 6)")
    module.main(run_id=uuid.uuid4().hex, router=args.router, config=args.config, scenario=args.scenario, reps=args.reps)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", choices=sorted(EXP_MODULES))
    parser.add_argument("--router")
    parser.add_argument("--config")
    parser.add_argument("--scenario")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()

    if args.selftest:
        sys.exit(run_selftests())
    if not args.exp:
        parser.error("one of --exp or --selftest is required")
    run_experiment(args)


if __name__ == "__main__":
    main()
