"""data selftest. Rule: must run in under 30 seconds, with no network and no keys.

Validates:
  1. canary.db exists and has 50 records with unique canaries
  2. permissions table has correct structure (intern=0 for all, manager=1 for all, support mixed)
  3. prompts_policy.json has 40 deny prompts each referencing a valid record + canary
  4. prompts_legit.json has 40 allow prompts with correct role/record pairings
  5. HMAC token generation and verification works
  6. HMAC token with wrong role/id is rejected
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# Ensure the project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA_DIR = Path(__file__).resolve().parent
DB_PATH = DATA_DIR / "canary.db"

# Rebuild if needed
if not DB_PATH.exists():
    from data.build_db import build_all
    build_all()

from data.build_db import make_hmac_token, verify_hmac_token

passed = 0
failed = 0


def check(desc: str, condition: bool, detail: str = "") -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {desc}")
    else:
        failed += 1
        msg = f"  [FAIL] {desc}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ── 1. Database structure ──────────────────────────────────────────────

print("1. Database structure")
conn = sqlite3.connect(str(DB_PATH))
conn.row_factory = sqlite3.Row

records = conn.execute("SELECT * FROM records").fetchall()
check("50 records exist", len(records) == 50, f"got {len(records)}")

canaries = [r["canary"] for r in records]
check("All canaries unique", len(canaries) == len(set(canaries)))

check("Canaries match ACCT-XXXX pattern",
      all(c.startswith("ACCT-") and len(c) == 9 for c in canaries),
      f"sample: {canaries[:3]}")

check("Every record has a non-empty body",
      all(r["body"] and len(r["body"]) > 10 for r in records))

check("Every body contains its canary",
      all(r["canary"] in r["body"] for r in records))

# ── 2. Permissions ─────────────────────────────────────────────────────

print("2. Permissions table")
perms = conn.execute("SELECT role, record_id, allowed FROM permissions").fetchall()
check("150 permission rows (3 roles × 50 records)", len(perms) == 150, f"got {len(perms)}")

intern_perms = conn.execute("SELECT allowed FROM permissions WHERE role='intern'").fetchall()
check("Intern has 0 allowed records", all(p["allowed"] == 0 for p in intern_perms))

manager_perms = conn.execute("SELECT allowed FROM permissions WHERE role='manager'").fetchall()
check("Manager has all 50 allowed", all(p["allowed"] == 1 for p in manager_perms))

support_perms = conn.execute("SELECT record_id, allowed FROM permissions WHERE role='support'").fetchall()
support_allowed = [p for p in support_perms if p["allowed"] == 1]
support_denied = [p for p in support_perms if p["allowed"] == 0]
check("Support has mixed permissions", len(support_allowed) > 0 and len(support_denied) > 0,
      f"allowed={len(support_allowed)}, denied={len(support_denied)}")

# Verify even-numbered records are allowed for support
even_support = conn.execute(
    "SELECT record_id, allowed FROM permissions WHERE role='support'"
).fetchall()
for p in even_support:
    idx = int(p["record_id"].split("-")[1])
    if idx % 2 == 0:
        check(f"Support allowed for even record {p['record_id']}", p["allowed"] == 1)
        break  # spot check one

conn.close()

# ── 3. Policy prompts ─────────────────────────────────────────────────

print("3. Policy prompts (deny)")
policy_path = DATA_DIR / "prompts_policy.json"
check("prompts_policy.json exists", policy_path.exists())

if policy_path.exists():
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    check("40 policy prompts", len(policy) == 40, f"got {len(policy)}")
    check("All expected=deny", all(p["expected"] == "deny" for p in policy))
    check("All role=intern", all(p["role"] == "intern" for p in policy))
    check("All have record_id", all(p["record_id"] is not None for p in policy))
    check("All have canary", all(p["canary"] is not None for p in policy))
    check("All have REQ: placeholder", all("REQ:{request_id}" in p["text"] for p in policy))

    # Verify canaries match database
    conn = sqlite3.connect(str(DB_PATH))
    for p in policy[:5]:  # spot-check first 5
        row = conn.execute("SELECT canary FROM records WHERE id=?", (p["record_id"],)).fetchone()
        if row:
            check(f"Policy prompt {p['id']} canary matches DB",
                  row[0] == p["canary"],
                  f"expected {row[0]}, got {p['canary']}")
    conn.close()

# ── 4. Legit prompts ──────────────────────────────────────────────────

print("4. Legit prompts (allow)")
legit_path = DATA_DIR / "prompts_legit.json"
check("prompts_legit.json exists", legit_path.exists())

if legit_path.exists():
    legit = json.loads(legit_path.read_text(encoding="utf-8"))
    check("40 legit prompts", len(legit) == 40, f"got {len(legit)}")
    check("All have REQ: placeholder", all("REQ:{request_id}" in p["text"] for p in legit))

    allow_prompts = [p for p in legit if p["expected"] == "allow"]
    allow_public = [p for p in legit if p["expected"] == "allow_public"]
    check("Mix of allow and allow_public", len(allow_prompts) > 0 and len(allow_public) > 0,
          f"allow={len(allow_prompts)}, public={len(allow_public)}")

    manager_legit = [p for p in legit if p["role"] == "manager"]
    support_legit = [p for p in legit if p["role"] == "support"]
    check("Has manager prompts", len(manager_legit) > 0, f"got {len(manager_legit)}")
    check("Has support prompts", len(support_legit) > 0, f"got {len(support_legit)}")

    # Verify support prompts reference even-numbered records (which they're allowed to see)
    conn = sqlite3.connect(str(DB_PATH))
    for p in support_legit[:3]:  # spot-check
        if p["record_id"]:
            perm = conn.execute(
                "SELECT allowed FROM permissions WHERE role='support' AND record_id=?",
                (p["record_id"],)
            ).fetchone()
            check(f"Support legit prompt {p['id']} references allowed record",
                  perm is not None and perm[0] == 1)
    conn.close()

    # Public prompts should have no canary
    for p in allow_public[:3]:
        check(f"Public prompt {p['id']} has no canary", p["canary"] is None)
        check(f"Public prompt {p['id']} has no record_id", p["record_id"] is None)

# ── 5. HMAC token ─────────────────────────────────────────────────────

print("5. HMAC token verification")
test_token = make_hmac_token("user-001", "manager", "req-abc")
check("Token is 64-char hex", len(test_token) == 64 and all(c in "0123456789abcdef" for c in test_token))

check("Valid token verifies", verify_hmac_token(test_token, "user-001", "manager", "req-abc"))
check("Wrong role rejected", not verify_hmac_token(test_token, "user-001", "intern", "req-abc"))
check("Wrong user rejected", not verify_hmac_token(test_token, "user-999", "manager", "req-abc"))
check("Wrong request_id rejected", not verify_hmac_token(test_token, "user-001", "manager", "req-xyz"))
check("Tampered token rejected", not verify_hmac_token("a" * 64, "user-001", "manager", "req-abc"))

# ── Summary ────────────────────────────────────────────────────────────

print(f"\ndata selftest: {passed} passed, {failed} failed")
if failed > 0:
    sys.exit(1)
print("data OK")
