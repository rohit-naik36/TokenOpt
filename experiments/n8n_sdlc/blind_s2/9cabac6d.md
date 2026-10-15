## Ticket
{
  "id": "T07",
  "title": "Cache product price lookups for 5 minutes",
  "type": "chore",
  "priority_hint": "Low",
  "reporter": "backend-dev",
  "labels": [
    "api",
    "pricing",
    "performance"
  ],
  "description": "`get_price(sku, currency)` hits the pricing table on every cart render and shows up as the top query in slow-log. Prices change at most a few times a day. Add an in-process cache with a 5-minute TTL.\n\nConstraints: cached entries are per SKU and per currency (the same SKU is sold in EUR, USD and INR at different prices, not converted). Expired entries must be refetched. No new dependencies.",
  "environment": "Python 3.12. Service: api. Single-process gunicorn workers (4 per pod), so per-process caching is acceptable for now.",
  "comments": [
    "backend-dev: Plain dict with timestamps is enough, no need for cachetools.",
    "pm: Pricing team confirms stale prices up to 5 minutes are acceptable."
  ]
}

## Diff
diff --git a/api/pricing.py b/api/pricing.py
--- a/api/pricing.py
+++ b/api/pricing.py
@@ -1,14 +1,28 @@
+import time
+
 from api.db import fetch_price_row

+TTL_SECONDS = 300
+_cache: dict[str, tuple[float, float]] = {}
+

 def get_price(sku: str, currency: str) -> float:
-    row = fetch_price_row(sku, currency)
-    return float(row["amount"])
+    now = time.monotonic()
+    hit = _cache.get(sku)
+    if hit is not None and now - hit[0] < TTL_SECONDS:
+        return hit[1]
+
+    row = fetch_price_row(sku, currency)
+    amount = float(row["amount"])
+    _cache[sku] = (now, amount)
+    return amount


## Stage output: triage
{"severity": "P2", "category": "chore", "component": "api", "summary": "Add a 5-minute in-process TTL cache to get_price(sku, currency) to cut repeated pricing-table queries seen as the top slow-log query. Entries are keyed per SKU and currency.", "risk_flags": ["stale prices for up to 5 minutes after a change", "per-process cache means each gunicorn worker holds its own copy", "cache growth across SKU and currency combinations needs a bound"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a shopper viewing my cart, I want product prices to load without repeated pricing-table queries so that cart pages render faster and the database is under less load", "acceptance_criteria": ["Given a SKU and currency pair whose price was fetched less than 5 minutes ago, when get_price(sku, currency) is called, then the price is returned from the in-process cache and the pricing table is not queried.", "Given a SKU and currency pair with no cached entry or whose cached entry is 5 minutes old or older, when get_price(sku, currency) is called, then the pricing table is queried and the fresh price is returned and stored in the cache.", "Given the same SKU requested in two different currencies (for example EUR and USD), when each is requested, then each currency returns its own independently cached price and the two entries do not overwrite or affect each other.", "Given a cached price for SKU X in EUR, when get_price is called for SKU X in INR, then the INR price is fetched from the pricing table and the cached EUR value is not returned or modified.", "Given the cache is in use, when get_price is called for any SKU and currency, then the function signature and return value are unchanged from the current behaviour, and no new third-party dependency is added to the project."], "non_goals": ["Cross-process or distributed caching (e.g. Redis or Memcached); the cache is in-process only.", "Explicit cache invalidation when a price is updated before the TTL expires.", "Currency conversion; prices are stored and cached per currency as-is.", "Caching of any data other than the output of get_price."], "open_questions": ["Should the 5-minute TTL be configurable via settings or environment variable, or is a fixed constant acceptable?", "What is the expected maximum number of distinct SKU and currency pairs, and is an unbounded in-process cache acceptable memory-wise or should a size limit and eviction policy be specified?", "Should a failed pricing-table query (error or timeout) be cached, or must errors always bypass the cache?", "Is stale-price exposure of up to 5 minutes acceptable for all price-dependent flows, including checkout totals, or should checkout bypass the cache?"]}

## Stage output: plan
{"steps": [{"id": 1, "description": "Read the existing get_price implementation and its pricing table query path to confirm the current signature, return type and any existing caching or memoisation so the change reuses them.", "files": ["api/pricing"]}, {"id": 2, "description": "Add a bounded in-process cache keyed on the (sku, currency) pair, storing each price with its fetch timestamp and a 5-minute time-to-live, using only the standard library so no new dependency is introduced.", "files": ["api/pricing/cache.py"]}, {"id": 3, "description": "Wrap the existing get_price body so it first checks the cache for a non-expired entry for the exact (sku, currency) key, returns it on a hit, and otherwise queries the pricing table, stores the result with the current timestamp, and returns it, keeping the signature and return value unchanged.", "files": ["api/pricing/service.py", "api/pricing/cache.py"]}, {"id": 4, "description": "Add a size bound and eviction policy to the cache so entries for many SKU and currency combinations cannot grow memory without limit, and make the cache a module-level instance that is safe for the threading model the API uses.", "files": ["api/pricing/cache.py"]}, {"id": 5, "description": "Add unit tests covering cache hit, cache miss, expired entry, per-currency isolation and signature stability, and an integration-style test asserting the pricing table is not queried on a hit.", "files": ["api/tests/pricing/test_get_price_cache.py", "api/tests/pricing/test_cache.py"]}, {"id": 6, "description": "Document in the pricing module docstring that the cache is per process, that each gunicorn worker holds its own copy, and that prices can be up to 5 minutes stale.", "files": ["api/pricing/service.py"]}], "risks": ["Prices can be up to 5 minutes stale after a change; mitigate by documenting the TTL in code and in the ticket, and by keeping the TTL as a single named constant so it can be tuned.", "Each gunicorn worker keeps its own cache, so the same SKU may return different prices across workers during the TTL window; mitigate by documenting this and confirming with product that per-worker consistency is acceptable.", "Unbounded growth across SKU and currency combinations could exhaust memory; mitigate with a maximum entry count and eviction in the cache module.", "Concurrent requests may race on cache writes and cause inconsistent reads; mitigate by using a lock or thread-safe structure around cache reads and writes.", "Changing get_price could alter behaviour for callers that rely on fresh data; mitigate by keeping the signature and return value identical and verifying callers in the test plan."], "test_plan": ["Given a price fetched less than 5 minutes ago for a SKU and currency, calling get_price returns the cached value and the pricing table query is not invoked (acceptance criterion 1).", "Given no cache entry for a SKU and currency, calling get_price queries the pricing table, returns the fresh price, and stores it in the cache (acceptance criterion 2).", "Given a cached entry that is exactly 5 minutes old or older, calling get_price queries the pricing table and replaces the cached entry (acceptance criterion 2).", "Given the same SKU requested in EUR and then USD, each call returns its own price and a later EUR call still returns the EUR value, not the USD value (acceptance criterion 3).", "Given a cached EUR price for SKU X, calling get_price for SKU X in INR fetches from the pricing table and does not return or modify the EUR entry (acceptance criterion 4).", "Assert get_price keeps its existing signature and return type, and that the project dependency manifest has no new third-party entries after the change (acceptance criterion 5).", "Fill the cache beyond its maximum size and assert the number of entries stays within the bound and that eviction occurs (risk mitigation for unbounded growth).", "Call get_price concurrently from multiple threads for the same key and assert no exceptions occur and returned values are consistent (risk mitigation for races)."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "api/pricing.py", "line": 11, "severity": "blocker", "issue": "The cache key is `sku` alone (`_cache.get(sku)`), so a price cached for SKU X in EUR is returned for SKU X in INR. This violates acceptance criteria 3 and 4 and returns wrong monetary amounts to callers.", "suggested_fix": "Key the cache on the tuple (sku, currency): `key = (sku, currency)`, then use `_cache.get(key)` and `_cache[key] = (now, amount)`, with the type annotated as `dict[tuple[str, str], tuple[float, float]]`."}, {"file": "api/pricing.py", "line": 6, "severity": "major", "issue": "The cache is unbounded (`_cache: dict[...] = {}`) and no eviction occurs, despite plan step 4 requiring a size bound. Expired entries are never removed, so memory grows with every distinct SKU and currency combination.", "suggested_fix": "Add a maximum size and evict expired or oldest entries on insert, for example with an OrderedDict-based LRU capped at a fixed number of entries, or prune expired keys when the bound is reached."}, {"file": "api/pricing.py", "line": 6, "severity": "major", "issue": "The module-level dict is read and written from `get_price` with no lock. The plan requires thread safety for the API's threading model; concurrent requests can race on the check-then-set sequence and on eviction once added.", "suggested_fix": "Guard reads and writes with a `threading.Lock` (or use a lock-protected helper class in cache.py as the plan describes) so cache operations are atomic."}, {"file": "api/pricing.py", "line": 14, "severity": "minor", "issue": "The cache lookup path and store are placed in `get_price` directly rather than in the planned `api/pricing/cache.py` and `api/pricing/service.py` structure, and no tests or docstring documenting the per-process, up-to-5-minutes-stale behaviour are included in the diff.", "suggested_fix": "Move the cache into `api/pricing/cache.py`, add the planned unit tests (hit, miss, expiry, per-currency isolation, signature stability), and document per-worker staleness in the module docstring."}]
, "summary": "The cache is keyed on SKU only, so EUR and INR prices collide and wrong amounts are returned. The cache is also unbounded and unsynchronised, and tests and docs from the plan are missing."}

## Stage output: release_note
{"title": "Product price lookups now cached for five minutes", "summary": "Product price lookups are now cached for up to five minutes. Repeated requests for the same product's price within that window are served from the cache instead of querying the pricing table on each call. This change is intended to reduce response time and database load.", "changes": ["Product price lookups are cached for five minutes.", "Repeated price lookups for the same product within the cache window no longer query the pricing table on each request."], "breaking": false, "upgrade_notes": ""}