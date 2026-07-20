"""test3 - prompt-cache metrics at 25 requests/min (above the ~15/min limit)."""

from app import run_cli
from rate_test_common import run_rate_test


def main() -> int:
    return run_rate_test(
        rpm=25,
        duration_seconds=120,
        cache_key="prompt-cache-rate-25",
        label="test3",
    )


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
