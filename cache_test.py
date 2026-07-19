import sys
import time

from app import (
    MODEL_DEPLOYMENT,
    PROMPT_CACHE_KEY,
    PROMPT_CACHE_RETENTION,
    cache_stats,
    create_openai_client,
    get_project_endpoint,
    run_cli,
)


# One reusable guideline sentence, repeated to build a large, stable prefix.
# Prompt caching only engages once at least 1,024 leading tokens are identical,
# so this block is deliberately oversized (~2,000 tokens) and must stay byte-for-
# byte identical across every request for cache reads to occur.
_GUIDELINE = (
    "Keep answers accurate, cite the relevant Azure service, prefer managed "
    "identities over secrets, and note any cost or quota implications for the "
    "recommended approach."
)
STABLE_PREFIX = (
    "You are a meticulous assistant for a cloud engineering team. Apply these "
    "standing operating guidelines to every response.\n\n"
    + "\n".join(f"Guideline {i}: {_GUIDELINE}" for i in range(1, 61))
)

# Short, varying questions. Only the trailing user turn changes, so the large
# leading prefix stays identical and remains eligible for cache reads.
QUESTIONS = [
    "In one sentence, what is Azure Blob Storage used for?",
    "In one sentence, what is Azure Key Vault used for?",
    "In one sentence, what is Azure Functions used for?",
    "In one sentence, what is Azure Kubernetes Service used for?",
]


def send_turn(client, question: str, cache_key: str = PROMPT_CACHE_KEY) -> tuple[int, int]:
    response = client.responses.create(
        model=MODEL_DEPLOYMENT,
        input=f"{STABLE_PREFIX}\n\nUser question: {question}",
        prompt_cache_key=cache_key,
        prompt_cache_retention=PROMPT_CACHE_RETENTION,
    )
    return cache_stats(response)


def run_test() -> int:
    client = create_openai_client(get_project_endpoint())
    print(
        f"Testing prompt caching on '{MODEL_DEPLOYMENT}' "
        f"(cache key: '{PROMPT_CACHE_KEY}', retention: in_memory)\n"
    )
    print(f"{'turn':<6}{'input_tokens':<14}{'cached_tokens':<15}{'hit?':<5}")
    print("-" * 40)

    first_input_tokens = 0
    hits_after_warmup = 0

    for turn, question in enumerate(QUESTIONS, start=1):
        input_tokens, cached = send_turn(client, question)
        if turn == 1:
            first_input_tokens = input_tokens
        elif cached > 0:
            hits_after_warmup += 1
        print(f"{turn:<6}{input_tokens:<14}{cached:<15}{'yes' if cached else 'no':<5}")
        time.sleep(1)  # stay well under the ~15 requests/min same-prefix cache limit

    print("-" * 40)

    if first_input_tokens < 1024:
        print(
            f"\nFAIL: prefix was only {first_input_tokens} tokens; caching requires "
            ">=1,024 identical leading tokens. Enlarge STABLE_PREFIX.",
            file=sys.stderr,
        )
        return 1

    if hits_after_warmup:
        print(
            f"\nPASS: {hits_after_warmup} of {len(QUESTIONS) - 1} post-warmup turns "
            "served cached tokens. In-memory prompt caching is working."
        )
        return 0

    print(
        "\nFAIL: no cache hits after the warm-up turn. Turn 1 writes the cache "
        "(cached_tokens=0) and later identical-prefix turns should read it. Re-run "
        "promptly \u2014 the in-memory cache expires after 5-10 min of inactivity.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(run_cli(run_test))
