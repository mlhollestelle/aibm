# Simulation Speedup Investigation

## Current Architecture

### LLM calls per agent (sequential)

Each agent in `_simulate_agent` makes these LLM calls **in sequence**:

| Step | Method | LLM calls | Depends on |
|------|--------|-----------|------------|
| 1 | `generate_persona()` | 1 | nothing |
| 2 | `choose_work_zone()` / `choose_school_zone()` | 0 or 1 | persona |
| 3 | `generate_activities()` | 1 | persona, work/school zone |
| 4 | `choose_destination()` (per flexible activity) | 0-N | activities |
| 5 | `schedule_activities()` | 1 | all activities with locations |
| 6 | `build_tours()` | 0 (pure logic) | schedule |
| 7 | `choose_tour_mode()` (per tour) | 1 per tour | tours |

**Typical total: 5-10 LLM calls per agent, all sequential.**

### Current bottlenecks

1. **Fully sequential** — agents are processed one-by-one in a `for` loop
   (`simulate.py:303-314`). No overlap between agents or within an agent.
2. **No async I/O** — all three LLM clients (`GeminiClient`, `AnthropicClient`,
   `OpenAIClient`) use synchronous HTTP calls that block the thread while
   waiting for the API response.
3. **Rate limiter sleeps** — `RateLimiter` uses `time.sleep()` when the rolling
   window is full, which blocks the single thread further.
4. **No caching** — identical or near-identical prompts (e.g. agents with the
   same demographics) are sent fresh every time.
5. **No batching** — every LLM call is a separate HTTP round-trip.

---

## Speedup Strategies

### Strategy 1: Concurrent agent processing (HIGH impact, MEDIUM effort)

**What:** Process multiple agents in parallel using `concurrent.futures.ThreadPoolExecutor`.

**Why it works:** Agents are independent of each other. While one agent waits
for an LLM API response (~200-1000ms), other agents can make their own calls.
This turns network latency from blocking to overlapping.

**Implementation sketch:**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=8) as pool:
    futures = {
        pool.submit(_simulate_agent, agent, hh, ...): agent
        for hh in households
        for agent in hh.members
    }
    for future in as_completed(futures):
        trip_rows, day_plan_row, activity_rows = future.result()
        all_trip_rows.extend(trip_rows)
        ...
```

**Considerations:**
- The `RateLimiter` must become thread-safe (replace `deque` + `time.sleep`
  with `threading.Lock` and `threading.Condition`).
- Set `max_workers` to balance concurrency against API rate limits. A good
  default is `rate_limit_rpm / avg_calls_per_minute_per_agent`.
- Very low effort to implement — only `simulate.py` and `RateLimiter` change.

**Expected speedup:** 4-10x depending on number of agents and rate limits.

---

### Strategy 2: Async LLM clients (HIGH impact, HIGH effort)

**What:** Rewrite the LLM clients to use `asyncio` with async HTTP libraries
(`httpx`, `aiohttp`, or provider-native async clients).

**Why it works:** Like Strategy 1 but more efficient — no thread overhead,
and the event loop can manage thousands of concurrent requests.

**Implementation sketch:**

```python
class AsyncOpenAIClient:
    async def generate_json(self, model, prompt, schema) -> str:
        response = await self._async_client.chat.completions.create(...)
        return response.choices[0].message.content
```

**Considerations:**
- All three providers offer async clients: `anthropic.AsyncAnthropic`,
  `openai.AsyncOpenAI`, `google.genai` with async support.
- Requires `async/await` throughout the call chain — `Agent` methods,
  `_simulate_agent`, the main loop all become async.
- Much larger refactor than Strategy 1, touches every module.

**Expected speedup:** 5-15x (same as threading but better resource usage).

**Recommendation:** Start with Strategy 1 (threading). Move to async only if
threading bottlenecks appear or you need >50 concurrent agents.

---

### Strategy 3: Combine LLM calls (MEDIUM impact, LOW effort)

**What:** Merge multiple sequential LLM steps into a single prompt.

**Candidates for merging:**
- **Persona + activities** → one call that returns both persona text and the
  activity list.
- **Scheduling + mode choice** → one call that returns the schedule and
  chooses modes for each tour.

**Example combined prompt:**

```
You are {name}, planning your day.
Demographics: ...

1. Write a 1-2 sentence persona.
2. List your out-of-home activities for today.
3. Assign start/end times to each activity.

Return JSON with keys: persona, activities (with type, is_flexible,
start_time, end_time).
```

**Considerations:**
- Reduces calls from ~7 to ~3-4 per agent (roughly halving latency).
- Larger prompts may produce less reliable structured output.
- Test carefully that combined prompts still produce valid results.

**Expected speedup:** 1.5-2x (fewer round-trips).

---

### Strategy 4: Prompt caching (LOW-MEDIUM impact, LOW effort)

**What:** Use provider-native prompt caching to speed up requests that share
long common prefixes.

**Provider support:**
- **Anthropic:** Automatic prompt caching for prefixes >=1024 tokens. System
  prompts and repeated context are cached. No code change needed if using a
  system message.
- **OpenAI:** Automatic prompt caching (since late 2024) for prompts sharing
  prefixes >=1024 tokens. 50% cost reduction, ~80% latency reduction on
  cache hits.
- **Gemini:** Explicit context caching API via `caching.CachedContent.create()`.
  Must create a cache object and reference it in subsequent calls.

**Implementation for this model:**
- Move the "You are {name}" background text to a system message rather than
  user message. This increases cache hit rate since the system message stays
  the same across calls for the same agent.
- For Gemini, create a cached context with the common background and zone
  data before the per-agent loop.

**Expected speedup:** 1.2-1.5x (mainly latency reduction on cache hits).

---

### Strategy 5: Local response caching (LOW impact, LOW effort)

**What:** Cache LLM responses locally (in-memory dict or on-disk SQLite)
keyed by `(model, prompt_hash, schema_hash)`. If the same prompt is sent
again, return the cached response.

**When it helps:**
- Multiple agents with identical demographics/backgrounds.
- Re-running the pipeline during development (avoids re-calling the API).
- Not useful for production runs where every agent is unique.

**Implementation sketch:**

```python
import hashlib, json, shelve

class CachingClient:
    def __init__(self, client, cache_path="llm_cache.db"):
        self._client = client
        self._cache = shelve.open(cache_path)

    def generate_json(self, model, prompt, schema):
        key = hashlib.sha256(
            json.dumps([model, prompt, schema]).encode()
        ).hexdigest()
        if key in self._cache:
            return self._cache[key]
        result = self._client.generate_json(model, prompt, schema)
        self._cache[key] = result
        return result
```

**Expected speedup:** Depends on cache hit rate — 0x for unique agents, up
to Nx for development re-runs.

---

### Strategy 6: Reduce per-agent LLM calls (MEDIUM impact, MEDIUM effort)

**What:** Replace some LLM calls with deterministic rules or simpler heuristics.

**Candidates:**
- **Destination choice for work/school zones:** Instead of asking the LLM,
  use a gravity model (weight by zone attractiveness / travel time). This
  removes 1 call per employed/student agent.
- **Mode choice:** Instead of LLM, use a simple utility-based logit model
  (cost + time + persona flags). Removes 1 call per tour.
- **Scheduling:** Use rule-based scheduling (work 8-17, school 8-15, etc.)
  with random perturbation. Removes 1 call.

**Considerations:**
- This fundamentally changes the model's philosophy (LLM-driven → hybrid).
- Losing the LLM's "reasoning" output may reduce interpretability.
- Best applied to steps where the LLM adds the least value.

**Expected speedup:** 1.3-2x (fewer API calls).

---

### Strategy 7: Use faster/cheaper models selectively (LOW impact, LOW effort)

**What:** Use a fast, cheap model (e.g. `gpt-4o-mini`, `gemini-2.0-flash-lite`)
for simple decisions and reserve a larger model for complex ones.

**Current state:** Config already uses `gpt-4o-mini` which is quite fast. The
`model` field on `Agent` is already per-agent, so different agents could use
different models.

**Possible assignment:**
- Persona generation → larger model (sets tone for all subsequent steps)
- Activity generation → larger model (creative task)
- Destination choice → smaller model (pick from a list)
- Scheduling → smaller model (assign numbers)
- Mode choice → smaller model (pick from 2-3 options)

**Expected speedup:** 1.1-1.3x (marginal latency difference between mini models).

---

## Recommended Implementation Order

| Priority | Strategy | Impact | Effort | Dependencies |
|----------|----------|--------|--------|-------------|
| 1 | **Concurrent agents** (threading) | HIGH | MEDIUM | Thread-safe rate limiter |
| 2 | **Combine LLM calls** | MEDIUM | LOW | None |
| 3 | **Prompt caching** | LOW-MED | LOW | None |
| 4 | **Local response caching** | LOW | LOW | None |
| 5 | **Reduce LLM calls** (heuristics) | MEDIUM | MEDIUM | Design decisions needed |
| 6 | **Async clients** | HIGH | HIGH | Full refactor of agent.py + llm.py |
| 7 | **Model tiering** | LOW | LOW | None |

### Quick wins (implementable now):

1. **Thread pool in `simulate.py`** + thread-safe `RateLimiter` — the single
   biggest speedup with minimal code changes.
2. **Combine persona + activities** into one LLM call — halves the sequential
   chain for the first half of each agent's simulation.
3. **Add a `CachingClient` wrapper** — instant speedup during development
   iteration.

### For scaling to hundreds of agents:

4. Move to async clients (Strategy 2) for better concurrency scaling.
5. Replace simple decisions with heuristics (Strategy 6) to reduce total API
   calls.

---

## Appendix: LLM call timeline for one agent

```
Time ──────────────────────────────────────────────────────>

Agent 1 (current — sequential):
[persona ████]  [work_zone ████]  [activities ████]
                                   [dest_1 ████]  [dest_2 ████]
                                                    [schedule ████]
                                                     [mode ████]
Total wall time: ~7 × avg_latency

Agent 1 (with combined calls):
[persona+activities ██████]  [dest_1 ████]  [dest_2 ████]
                              [schedule+mode ██████]
Total wall time: ~4 × avg_latency

Multiple agents (with threading):
Agent 1: [persona ████]  [work ████]  [activities ████] ...
Agent 2: [persona ████]  [activities ████]  [dest ████] ...
Agent 3: [persona ████]  [work ████]  [activities ████] ...
Agent 4: [persona ████]  [activities ████]  [dest ████] ...
Total wall time: ~max(agent_times) instead of sum(agent_times)
```
