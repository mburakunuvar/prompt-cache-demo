# Prompt-cache rate tests — results summary

**Date:** 2026-07-19 · **Model:** `gpt-5-mini` · **Retention:** `in_memory`
**Runners:** [rate_test_10.py](rate_test_10.py), [rate_test_15.py](rate_test_15.py), [rate_test_25.py](rate_test_25.py) via [rate_test_common.py](rate_test_common.py)

## Statement under test

> If requests for the same prefix and `prompt_cache_key` combination exceed
> approximately 15 requests per minute, some requests might miss the cache.

Each test drives the fixed ~2,021-token prefix (only the trailing question
varies) at a target rate for ~120s, with a distinct cache key per test, and reads
`response.usage.input_tokens_details.cached_tokens` per request.

## Consolidated results

| Test | Target | **Achieved** | Requests | Warm-up (turn 1) | Post-warm-up hits | Misses | Hit rate | Errors |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test1 | 10/min | **10.0/min** | 20 | `cached=0` (write) | 19/19 | 0 | **100.0%** | 0 |
| test2 | 15/min | **11.2/min** | 23 | `cached=0` (write) | 21/22 | 1 | **95.5%** | 0 |
| test3 | 25/min | **11.0/min** | 22 | `cached=0` (write) | 21/21 | 0 | **100.0%** | 0 |

On every cache read, 1920 of ~2,021 input tokens were served from cache (the
trailing question is never cached). No throttling (`429`/ERROR) occurred.

## Key finding — tests were latency-bound, not rate-limited

The **achieved** rate never exceeded ~11/min, even for the 15/min and 25/min
targets. Each Responses call to `gpt-5-mini` with the ~2,021-token prefix takes
~5–6s, which is longer than the target send intervals (4.0s at 15/min, 2.4s at
25/min). With **sequential** even-spacing, throughput is therefore capped at
~10–11/min regardless of target.

Consequence: **test3 did not actually exceed the ~15/min threshold**, so the
documented ">15/min → some misses" behaviour was **not exercised**. Its 100% hit
rate reflects an effective ~11/min load, not a passing stress test.

## Interpretation

- **test1 (10/min):** Valid control. Ran at the intended rate, 100% post-warm-up
  hits — consistent with being below the limit.
- **test2 (15/min):** Achieved ~11.2/min with a single miss (95.5%). Because the
  actual rate stayed below 15/min, that one miss is best attributed to normal
  cache variance/eviction rather than rate-limit pressure.
- **test3 (25/min):** Inconclusive for the limit. Sequential dispatch could not
  push past ~11/min, so the >15/min condition was never met.

The caching mechanism itself is confirmed working (stable warm-up write followed
by consistent ~1920-token reads); what remains unverified is the miss behaviour
*above* 15/min.

## Recommendation

To empirically trigger the documented misses, the target rate must actually be
sustained above 15/min. With ~5–6s per call that requires **concurrent
dispatch** (threads/async) rather than sequential spacing — e.g. keep several
requests in flight so the real send rate reaches 20–30/min. This was a
deliberate earlier trade-off (sequential was chosen for simplicity); revisiting
it is the logical next step. Note the added cost: a true 25/min × 2-min run is
~50 requests × ~2,021 tokens.

## Raw console output

### test1 — 10/min (achieved 10.0/min, 100%)

```text
req  t+s     input_tokens  cached_tokens  hit?
1    0.0     2021          0              no
2    12.5    2021          1920           yes
... (turns 3-20 all hit; 1920 cached each)
Summary: sent 20 (0 err), post-warm-up hits 19/19, hit rate 100.0%
```

### test2 — 15/min (achieved 11.2/min, 95.5%)

```text
req  t+s     input_tokens  cached_tokens  hit?
1    0.0     2021          0              no
2    9.1     2021          1920           yes
... (hits through turn 21)
22   113.1   2021          0              no     <- lone miss
23   117.5   2020          1920           yes
Summary: sent 23 (0 err), post-warm-up hits 21/22, hit rate 95.5%
```

### test3 — 25/min (achieved 11.0/min, 100%)

```text
req  t+s     input_tokens  cached_tokens  hit?
1    0.0     2021          0              no
2    9.3     2021          1920           yes
... (turns 3-22 all hit; 1920 cached each)
Summary: sent 22 (0 err), post-warm-up hits 21/21, hit rate 100.0%
achieved rate 11.0/min — did NOT reach the 25/min target (latency-bound)
```
