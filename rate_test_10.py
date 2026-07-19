"""test1 - prompt-cache hit rate at 10 requests/min (below the ~15/min limit)."""

from app import run_cli
from rate_test_common import run_rate_test


def main() -> int:
    return run_rate_test(
        rpm=10,
        duration_seconds=120,
        cache_key="prompt-cache-rate-10",
        label="test1",
    )


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
