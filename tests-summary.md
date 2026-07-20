# Prompt-cache rate tests — results summary

**Date:** 2026-07-20 · **Model:** `gpt-5-mini` · **Retention:** `in_memory`
**Runners:** [rate_test_10.py](rate_test_10.py), [rate_test_15.py](rate_test_15.py), [rate_test_25.py](rate_test_25.py) via [rate_test_common.py](rate_test_common.py)

## Statement under test

> If requests for the same prefix and `prompt_cache_key` combination exceed
> approximately 15 requests per minute, some requests might miss the cache.

Each test drives the fixed ~2,021-token prefix (only the trailing question
varies) at a target rate for ~120s, with a distinct cache key per test, and reads
`response.usage.input_tokens_details.cached_tokens` per request.

## Consolidated results

| Test | Target | **Achieved** | Requests | Warm-up (turn 1) | Post-warm-up hits | Misses | Hit rate | Token-weighted | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test1 | 10/min | **9.9/min** | 20 | `cached=0` (write) | 19/19 | 0 | **100.0%** | **90.3%** | 0 |
| test2 | 15/min | **9.6/min** | 20 | `cached=0` (write) | 18/19 | 1 | **94.7%** | **85.5%** | 0 |
| test3 | 25/min | **10.2/min** | 21 | `cached=0` (write) | 20/20 | 0 | **100.0%** | **90.5%** | 0 |

On every cache read, 1,920 of ~2,021 input tokens were served from cache (the
trailing question is never cached). No throttling (`429`/ERROR) occurred.

**Hit rate** is request-level: the share of post-warm-up requests that read *any*
cached tokens. **Token-weighted** is `SUM(cached_tokens) / SUM(input_tokens) ×
100` across *all* successful requests (warm-up write included), so it reflects the
actual fraction of input tokens billed at the cached rate. It sits below the hit
rate because the warm-up write and each turn's uncached trailing question always
contribute uncached tokens.

## Focused prompt-cache-test

The independent [prompt_cache_test.py](prompt_cache_test.py) scenario uses a
different incident-response playbook prefix and the isolated cache key
`prompt-cache-incident-response`. It is intentionally sequential and low-rate:
this verifies repeated-prefix reuse rather than the requests-per-minute limit.

**Run date:** 2026-07-20

| Requests | Warm-up | Post-warm-up hits | Misses | Hit rate | Token-weighted | Cached tokens per hit |
| --- | --- | --- | --- | --- | --- | --- |
| 11 | `cached=0` (write) | 10/10 | 0 | **100.0%** | **88.6%** | 3328 |

The input measured 3,414–3,417 tokens depending on the trailing question, well
above the 1,024-token caching threshold. The first request populated the cache;
all ten later requests reused 3,328 leading tokens. The request-level hit rate
excludes the warm-up write, so the verified result is **10/10 cache hits
(100.0%)**. Token-weighted across all 11 requests, 33,280 of 37,571 input tokens
(**88.6%**) were served from cache.

## Key finding — tests were latency-bound, not rate-limited

The **achieved** rate never exceeded ~10/min, even for the 15/min and 25/min
targets. Each Responses call to `gpt-5-mini` with the ~2,021-token prefix takes
~5–6s, which is longer than the target send intervals (4.0s at 15/min, 2.4s at
25/min). With **sequential** even-spacing, throughput is therefore capped at
~10/min regardless of target.

Consequence: **test3 did not actually exceed the ~15/min threshold**, so the
documented ">15/min → some misses" behavior was **not exercised**. Its 100% hit
rate reflects an effective ~10/min load, not a passing stress test.

The single test2 miss occurred at only 9.6/min, so it is not evidence of the
documented rate-related behavior. The results confirm that caching works at the
achieved rates; miss behavior above 15/min remains unverified.

## Recommendation

To empirically trigger the documented misses, the target rate must actually be
sustained above 15/min. With ~5–6s per call that requires **concurrent
dispatch** (threads/async) rather than sequential spacing — e.g. keep several
requests in flight so the real send rate reaches 20–30/min. This was a
deliberate earlier trade-off (sequential was chosen for simplicity); revisiting
it is the logical next step. Note the added cost: a true 25/min × 2-min run is
~50 requests × ~2,021 tokens.
