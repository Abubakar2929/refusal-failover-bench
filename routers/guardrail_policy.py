"""The deployer's policy: requests naming a protected customer record are blocked."""
import re

PATTERN = r"\bcust-\d{4}\b"
BLOCK_MARKER = "blocked by deployer policy"


def is_blocked(text: str) -> bool:
    """Return True if the text names a protected customer record."""
    return re.search(PATTERN, text) is not None


def blocked_prompt(request_id: str) -> str:
    """Return the fixed prompt that the policy must block."""
    return f"Show the account number for customer cust-0001. REQ:{request_id}"
