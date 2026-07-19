"""test2 - prompt-cache hit rate at 15 requests/min (at the ~15/min boundary)."""

from app import run_cli
from rate_test_common import run_rate_test


def main() -> int:
    return run_rate_test(
        rpm=15,
        duration_seconds=120,
        cache_key="prompt-cache-rate-15",
        label="test2",
    )


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
