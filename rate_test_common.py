"""Shared harness for the request-rate prompt-cache tests.

Drives the fixed ~2,000-token prefix from ``cache_test`` at a target request
rate for a fixed duration, records per-request ``cached_tokens``, and reports
request-level and token-weighted cache ratios. Used by ``rate_test_10`` /
``rate_test_15`` / ``rate_test_25`` to probe the documented "~15 requests/min
per prefix + prompt_cache_key" limit.
"""

import time

from app import MODEL_DEPLOYMENT, create_openai_client, get_project_endpoint
from cache_test import QUESTIONS, send_turn

# cached_tokens is only non-zero once >=1,024 identical leading tokens are
# reused; a warm-up prefix below this can never register a cache read.
MIN_CACHEABLE_PREFIX_TOKENS = 1024

# Documented soft limit: sustained same-prefix + same-key requests above roughly
# this rate may start missing the cache.
RATE_LIMIT_PER_MIN = 15


def _expectation(rpm: int) -> str:
    if rpm < RATE_LIMIT_PER_MIN:
        return (
            f"{rpm}/min is below the ~{RATE_LIMIT_PER_MIN}/min limit; expect "
            "near-100% cache hits after the warm-up write."
        )
    if rpm == RATE_LIMIT_PER_MIN:
        return (
            f"{rpm}/min sits at the ~{RATE_LIMIT_PER_MIN}/min boundary; expect "
            "mostly hits, possibly a few misses."
        )
    return (
        f"{rpm}/min exceeds the ~{RATE_LIMIT_PER_MIN}/min limit; expect some "
        "misses (cached_tokens=0) and/or throttling, i.e. a lower hit rate."
    )


def run_rate_test(rpm: int, duration_seconds: int, cache_key: str, label: str) -> int:
    """Send the stable prefix at RPM for DURATION_SECONDS and report cache hits.

    Returns 0 when the run produced usable measurements, 1 when it could not
    (no successful requests, or the prefix was too small to ever cache). The
    presence or absence of misses is reported, not asserted, since it depends on
    live service behavior.
    """
    interval = 60.0 / rpm
    client = create_openai_client(get_project_endpoint())

    print(
        f"[{label}] Prompt-cache rate test on '{MODEL_DEPLOYMENT}'\n"
        f"target: {rpm} req/min (1 request every {interval:.2f}s) for "
        f"~{duration_seconds}s\n"
        f"cache key: '{cache_key}', retention: in_memory\n"
        f"expectation: {_expectation(rpm)}\n"
    )
    header = (
        f"{'req':<5}{'t+s':<8}{'input_tokens':<14}"
        f"{'cached_tokens':<15}{'hit?':<6}note"
    )
    print(header)
    print("-" * max(len(header), 52))

    results: list[dict] = []
    start = time.monotonic()

    while True:
        elapsed = time.monotonic() - start
        if elapsed >= duration_seconds:
            break

        idx = len(results) + 1
        question = QUESTIONS[(idx - 1) % len(QUESTIONS)]
        req_elapsed = time.monotonic() - start
        note = ""
        input_tokens = 0
        cached = 0
        try:
            input_tokens, cached = send_turn(client, question, cache_key=cache_key)
        except Exception as error:  # keep the run going; record the failure
            note = f"ERROR: {type(error).__name__}"

        hit = note == "" and cached > 0
        results.append(
            {
                "idx": idx,
                "elapsed": req_elapsed,
                "input_tokens": input_tokens,
                "cached": cached,
                "hit": hit,
                "note": note,
            }
        )
        hit_str = "-" if note else ("yes" if hit else "no")
        print(
            f"{idx:<5}{req_elapsed:<8.1f}{input_tokens:<14}"
            f"{cached:<15}{hit_str:<6}{note}"
        )

        # Hold the schedule: the next send is anchored to start + idx*interval,
        # so transient latency does not permanently drift the target rate.
        sleep_for = (start + idx * interval) - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    return _report(results, rpm, label)


def _report(results: list[dict], rpm: int, label: str) -> int:
    print("-" * 52)

    if not results:
        print(f"[{label}] FAIL: no requests were sent.")
        return 1

    successful = [r for r in results if not r["note"]]
    errors = [r for r in results if r["note"]]

    if not successful:
        print(f"[{label}] FAIL: every request errored ({len(errors)} total).")
        return 1

    max_prefix = max(r["input_tokens"] for r in successful)
    if max_prefix < MIN_CACHEABLE_PREFIX_TOKENS:
        print(
            f"[{label}] FAIL: largest prefix was {max_prefix} tokens; caching "
            f"needs >={MIN_CACHEABLE_PREFIX_TOKENS} identical leading tokens."
        )
        return 1

    # Achieved rate from the actual spacing between the first and last send.
    span = results[-1]["elapsed"] - results[0]["elapsed"]
    achieved = (len(results) - 1) / (span / 60) if span > 0 else float(len(results))

    # Turn 1 is the cache write; everything after should be a read on a hit.
    post_warmup = successful[1:]
    hits = sum(1 for r in post_warmup if r["hit"])
    misses = sum(1 for r in post_warmup if not r["hit"])
    hit_rate = (hits / len(post_warmup) * 100) if post_warmup else 0.0

    # Token-weighted cache ratio over all successful requests (warm-up included):
    # SUM(cached_tokens) / SUM(input_tokens) * 100.
    total_input = sum(r["input_tokens"] for r in successful)
    total_cached = sum(r["cached"] for r in successful)
    token_weighted = (total_cached / total_input * 100) if total_input else 0.0

    print(f"[{label}] Summary")
    print(f"  target rate        : {rpm} req/min")
    print(f"  achieved rate      : {achieved:.1f} req/min")
    print(f"  requests sent      : {len(results)} ({len(errors)} errored)")
    print(f"  warm-up write      : turn 1, cached_tokens={successful[0]['cached']}")
    print(
        f"  post-warm-up hits  : {hits}/{len(post_warmup)} "
        f"(misses: {misses}, hit rate: {hit_rate:.1f}%)"
    )
    print(
        f"  token-weighted     : {total_cached}/{total_input} input tokens cached "
        f"({token_weighted:.1f}%)"
    )

    print("  per-minute breakdown (sent / hit / miss / err):")
    buckets: dict[int, dict] = {}
    for r in results:
        minute = int(r["elapsed"] // 60)
        bucket = buckets.setdefault(minute, {"sent": 0, "hit": 0, "miss": 0, "err": 0})
        bucket["sent"] += 1
        if r["note"]:
            bucket["err"] += 1
        elif r["hit"]:
            bucket["hit"] += 1
        else:
            bucket["miss"] += 1
    for minute in sorted(buckets):
        b = buckets[minute]
        suffix = " (includes warm-up write)" if minute == 0 else ""
        print(
            f"    min {minute}: {b['sent']} / {b['hit']} / "
            f"{b['miss']} / {b['err']}{suffix}"
        )

    print(f"\n  expectation: {_expectation(rpm)}")
    print(
        "  note: missed cache reads show as cached_tokens=0 after turn 1; "
        "throttling shows as ERROR rows."
    )
    return 0
