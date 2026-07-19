import os
import sys

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv


MODEL_DEPLOYMENT = "gpt-5-mini"
EXIT_COMMANDS = {"exit", "quit"}
# Stable key reused on every request so shared prompt prefixes route to the same
# in-memory cache. Extended (24h) retention is intentionally left disabled.
PROMPT_CACHE_KEY = "prompt-cache-demo"
PROMPT_CACHE_RETENTION = "in_memory"

_AUTH_HINT = (
    "Confirm that you ran 'az login', selected the correct subscription, "
    "and have access to the Foundry project."
)


def get_project_endpoint() -> str:
    load_dotenv()
    endpoint = os.getenv("PROJECT_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError(
            "PROJECT_ENDPOINT is not configured. Copy .env.example to .env "
            "and set the Foundry project endpoint."
        )
    return endpoint


def cache_stats(response) -> tuple[int, int]:
    """Return (input_tokens, cached_tokens) from a Responses API result."""
    usage = getattr(response, "usage", None)
    details = getattr(usage, "input_tokens_details", None)
    total = getattr(usage, "input_tokens", 0) or 0
    cached = getattr(details, "cached_tokens", 0) or 0
    return total, cached


def run_cli(callback) -> int:
    """Run CALLBACK with shared configuration and auth error handling."""
    try:
        return callback()
    except ValueError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"Foundry request failed: {error}", file=sys.stderr)
        print(_AUTH_HINT, file=sys.stderr)
        return 1


def create_openai_client(project_endpoint: str):
    project = AIProjectClient(
        endpoint=project_endpoint,
        credential=DefaultAzureCredential(),
    )
    return project.get_openai_client()


def run_chat() -> int:
    client = create_openai_client(get_project_endpoint())
    previous_response_id = None

    print(f"Connected to deployment: {MODEL_DEPLOYMENT}. Type 'exit' to quit.")

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if prompt.lower() in EXIT_COMMANDS:
            break
        if not prompt:
            continue

        request = {
            "model": MODEL_DEPLOYMENT,
            "input": prompt,
            "prompt_cache_key": PROMPT_CACHE_KEY,
            "prompt_cache_retention": PROMPT_CACHE_RETENTION,
        }
        if previous_response_id:
            request["previous_response_id"] = previous_response_id

        response = client.responses.create(**request)
        previous_response_id = response.id
        print(f"\nAssistant: {response.output_text}")

        total, cached = cache_stats(response)
        if total:
            print(f"[cache] {cached}/{total} input tokens served from cache")

    print("Goodbye.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(run_chat))