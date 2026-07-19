"""Measure prompt-cache hits for a stable incident-response playbook."""

import sys
import time

from app import (
    MODEL_DEPLOYMENT,
    PROMPT_CACHE_RETENTION,
    cache_stats,
    create_openai_client,
    get_project_endpoint,
    run_cli,
)


PROMPT_CACHE_KEY = "prompt-cache-incident-response"
MIN_CACHEABLE_PREFIX_TOKENS = 1024

_PLAYBOOK_RULE = (
    "Confirm impact and scope from observable evidence; preserve timestamps and "
    "correlation identifiers; prefer reversible mitigations; assign an owner and "
    "next checkpoint; communicate known facts separately from hypotheses; protect "
    "credentials and customer data; and record every action for the post-incident "
    "review."
)
STABLE_PREFIX = (
    "You are the incident commander assistant for a production engineering team. "
    "Apply this standing response playbook to every incident question. Keep each "
    "answer to one concise action-oriented sentence.\n\n"
    + "\n".join(f"Playbook rule {number}: {_PLAYBOOK_RULE}" for number in range(1, 61))
)

QUESTIONS = [
    "The API error rate doubled after a deployment. What is the first action?",
    "A database is rejecting new connections. What should the team verify first?",
    "A queue backlog is growing rapidly. What immediate signal matters most?",
    "A regional endpoint is timing out. What mitigation should be considered?",
    "Authentication failures spiked without a release. What should be checked?",
    "A storage dependency is returning throttling responses. What is the next step?",
    "Several pods are restarting repeatedly. What evidence should be collected?",
    "Customer latency increased while CPU stayed normal. What should be compared?",
    "A secret may have appeared in logs. What immediate action is required?",
    "The primary health probe is failing intermittently. What should be validated?",
    "Service recovered after rollback. What must happen before closing the incident?",
]


def send_turn(client, question: str) -> tuple[int, int]:
    response = client.responses.create(
        model=MODEL_DEPLOYMENT,
        input=f"{STABLE_PREFIX}\n\nIncident question: {question}",
        prompt_cache_key=PROMPT_CACHE_KEY,
        prompt_cache_retention=PROMPT_CACHE_RETENTION,
    )
    return cache_stats(response)


def run_test() -> int:
    client = create_openai_client(get_project_endpoint())
    print(
        f"[prompt-cache-test] Testing '{MODEL_DEPLOYMENT}' with incident-response "
        f"prompts\ncache key: '{PROMPT_CACHE_KEY}', retention: "
        f"{PROMPT_CACHE_RETENTION}\n"
    )
    print(f"{'turn':<6}{'input_tokens':<14}{'cached_tokens':<15}{'result'}")
    print("-" * 48)

    measurements: list[tuple[int, int]] = []
    for turn, question in enumerate(QUESTIONS, start=1):
        input_tokens, cached_tokens = send_turn(client, question)
        measurements.append((input_tokens, cached_tokens))
        result = "warm-up write" if turn == 1 else ("hit" if cached_tokens else "miss")
        print(f"{turn:<6}{input_tokens:<14}{cached_tokens:<15}{result}")
        time.sleep(1)

    print("-" * 48)
    first_input_tokens = measurements[0][0]
    if first_input_tokens < MIN_CACHEABLE_PREFIX_TOKENS:
        print(
            f"FAIL: warm-up input was only {first_input_tokens} tokens; prompt "
            f"caching requires at least {MIN_CACHEABLE_PREFIX_TOKENS} identical "
            "leading tokens.",
            file=sys.stderr,
        )
        return 1

    post_warmup = measurements[1:]
    if not post_warmup:
        print("FAIL: no post-warm-up cache reads were attempted.", file=sys.stderr)
        return 1

    hits = sum(1 for _, cached_tokens in post_warmup if cached_tokens > 0)
    misses = len(post_warmup) - hits
    hit_rate = hits / len(post_warmup) * 100
    print(
        f"RESULT: {hits}/{len(post_warmup)} post-warm-up cache hits "
        f"({hit_rate:.1f}% hit rate, {misses} misses)."
    )

    if hits == 0:
        print(
            "FAIL: no cached tokens were served after the warm-up write.",
            file=sys.stderr,
        )
        return 1

    print("PASS: in-memory prompt caching served at least one repeated prefix.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(run_test))
