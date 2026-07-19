# Prompt caching demo — Foundry `gpt-5-mini`

A minimal terminal demo that exercises and verifies **Azure OpenAI prompt
caching** on a `gpt-5-mini` deployment in a Microsoft Foundry project, via the
Responses API (`azure-ai-projects` → `get_openai_client()`).

- [app.py](app.py) — interactive chat. Follow-up prompts retain the context of
  earlier responses (via `previous_response_id`) for the life of the process,
  and each reply prints a cache-usage line.
- [cache_test.py](cache_test.py) — automated check that a long, identical prompt
  prefix produces cache reads. Exit code `0` = PASS, `1` = FAIL, `2` = config
  error.

## Deployment facts

Private identifiers are redacted below. The real values live only in gitignored
files — `.env` (endpoint) and `SECRETS.local.md` (all identifiers). See
[Secrets and private values](#secrets-and-private-values).

| Item | Value |
| --- | --- |
| Resource group | `***` |
| Foundry account | `***` |
| Foundry project | `***` |
| Model / version | `gpt-5-mini` / `2025-08-07` |
| SKU | GlobalStandard |
| Capacity | 252 |
| Supported APIs | Chat Completions, Responses, Agents V2, Assistants |
| Project endpoint | `https://***.services.ai.azure.com/api/projects/***` |

## Prerequisites

- Python 3.10 or later
- Azure CLI
- Access to your Foundry project and its model deployment

## Set up

Run these commands in PowerShell from this directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
az login
```

If your account has access to multiple Azure subscriptions, select the one that
contains your Foundry resource group:

```powershell
az account set --subscription "<subscription name or ID>"
```

Then edit `.env` and set `PROJECT_ENDPOINT` to your real Foundry project endpoint
(the committed `.env.example` ships only with a `<placeholder>` template; the real
value is in `SECRETS.local.md`).

## Run the chat app

```powershell
python app.py
```

Enter a prompt and then a dependent follow-up, such as:

```text
You: What is the capital of France?
You: Summarize that answer in three words.
```

Type `exit` or `quit`, or press `Ctrl+C`, to end the session.

## Run the cache test

```powershell
python cache_test.py
```

The test sends a fixed ~2,000-token prefix plus a short, varying question four
times, then reports per-turn `input_tokens` / `cached_tokens`.

## How prompt caching works

- `cached_tokens` is only non-zero once at least **1,024 identical leading
  tokens** are reused; hits then extend in 128-token increments.
- Every request sends `prompt_cache_key="prompt-cache-demo"` (stable routing) and
  `prompt_cache_retention="in_memory"`. Extended (24h) retention is intentionally
  **disabled** (and not offered for `gpt-5-mini`).
- After each response, `app.py` prints a line read from
  `response.usage.input_tokens_details.cached_tokens`:

  ```text
  [cache] 1920/2021 input tokens served from cache
  ```

- In the interactive app, short prompts show `[cache] 0/<n>` on early turns; hits
  appear once the accumulated conversation prefix grows past ~1,024 tokens.

## Verified test report

**Date:** 2026-07-18 · **Result:** ✅ PASS — in-memory prompt caching confirmed.

Configuration is the standing `prompt_cache_key` / `in_memory` retention described
above, with `previous_response_id` unused so every call sends the full,
byte-identical prefix.

Results:

```text
turn  input_tokens  cached_tokens  hit?
----------------------------------------
1     2021          0              no
2     2021          1920           yes
3     2020          1920           yes
4     2021          1920           yes
----------------------------------------
PASS: 3 of 3 post-warmup turns served cached tokens.
```

- **Turn 1** is a cache **write** (fresh prefix, `cached_tokens = 0`).
- **Turns 2–4** are cache **reads** (`1920` of ~2,021 input tokens served from
  cache; the trailing question is not cached).

Reproduce with `az login` then `python cache_test.py`.

## Issues found & fixes

| # | Symptom | Root cause | Fix |
| --- | --- | --- | --- |
| 1 | `getaddrinfo failed` / `APIConnectionError` | Endpoint host was `...ai.azure.com` (does not resolve) | Use `...services.ai.azure.com` in `.env` / `.env.example` |
| 2 | `400 invalid_request_error` on `input[1]` | v1 endpoint rejected bare `{role, content}` list items | Send a single-string `input` (prefix first, question last) |

## Troubleshooting

- `PROJECT_ENDPOINT is not configured`: copy `.env.example` to `.env` and run
  from this directory.
- Authentication or authorization failure: run `az login`, select the correct
  subscription, and confirm your identity has access to the Foundry project.
- Deployment not found: confirm the deployment name is `gpt-5-mini` in your
  Foundry project.

## Caveats & limits

- The **in-memory cache expires** after 5–10 min of inactivity (and always within
  1 hour), so a re-run after a long gap shows `cached_tokens = 0` on turn 1 again.
- A single character change in the prefix forces a cache miss.
- Sending the same prefix + key above **~15 requests/min** may miss the cache.
- Caches are **not shared across Azure subscriptions**.

## Secrets and private values

Private data is never committed. Committed files show `***` (or a `<placeholder>`);
the real values live only in gitignored files:

| Where | Contents | Committed? |
| --- | --- | --- |
| `.env` | `PROJECT_ENDPOINT` plus any runtime secrets/keys the app reads | No (gitignored) |
| `SECRETS.local.md` | Human-readable identifiers (RG, account, project, endpoint) | No (gitignored) |
| `.env.example` | Placeholder template only | Yes |

To run locally: `Copy-Item .env.example .env`, then fill in the real values from
`SECRETS.local.md`. Handle any future credential or key the same way — put the
secret in `.env` (or `SECRETS.local.md`), keep a `<placeholder>` in `.env.example`,
and reference it as `***` in committed docs. The `.gitignore` rules `.env.*`
(except `.env.example`), `*.local.md`, and `.secrets/` keep these out of git.