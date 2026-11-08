"""contracts selftest. Rule: must run in under 30 seconds, with no network and no keys."""
import json
from pathlib import Path

from contracts.fixtures.stub_adapter import StubAdapter
from contracts.schemas import read_logs

HERE = Path(__file__).resolve().parent


def main() -> None:
    scenarios = json.loads((HERE / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    ids = [s["id"] for s in scenarios]
    assert len(ids) == 11 and len(set(ids)) == 11, f"expected 11 unique scenario ids, got {ids}"

    files = sorted((HERE / "fixtures" / "sample_logs").glob("exp_*.jsonl"))
    total = sum(len(read_logs(str(p))) for p in files)
    assert total >= 30, f"expected at least 30 sample log lines, got {total}"

    adapter = StubAdapter()
    normal = adapter.send("hello REQ:abcd1234", "abcd1234")
    assert normal.reported_model == "mock-a" and normal.final_text == "OK ANSWERED_BY=mock-a", normal
    rerouted = adapter.send("REROUTE REQ:abcd1234", "abcd1234")
    assert rerouted.reported_model == "mock-b" and rerouted.final_text == "OK ANSWERED_BY=mock-b", rerouted

    print(f"contracts OK ({len(ids)} scenarios, {total} sample log lines in {len(files)} files, StubAdapter routes correctly)")


if __name__ == "__main__":
    main()
