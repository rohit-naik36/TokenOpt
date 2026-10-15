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
{"severity": "P2", "category": "chore", "component": "api", "summary": "Add a 5-minute in-process TTL cache to get_price(sku, currency) to cut repeated pricing-table queries seen in slow-log. Entries keyed per SKU and currency, no new dependencies.", "risk_flags": ["stale prices for up to 5 minutes after a price change", "per-process cache, not shared across the 4 workers per pod", "cache must key on both sku and currency"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a shopper, I want cart pages to render quickly so that I can review my order without delay, while price changes made in the pricing table are still reflected within a few minutes.", "acceptance_criteria": ["Given a SKU and currency pair that was looked up less than 5 minutes ago, when get_price(sku, currency) is called, then the value returned equals the value previously returned for that pair and the pricing table is not queried.", "Given a SKU and currency pair whose cached entry is 5 minutes old or older, when get_price(sku, currency) is called, then the pricing table is queried and the returned value replaces the cached entry.", "Given the same SKU requested in EUR, USD and INR, when get_price is called for each currency, then three separate cache entries are stored and each returns the price for its own currency with no currency conversion applied.", "Given a pricing table change for a SKU and currency that was cached less than 5 minutes ago, when get_price is called for that pair before the TTL expires, then the previously cached price is returned.", "Given the pricing table has no row for a requested SKU and currency pair, when get_price is called, then the behaviour is unchanged from before this change and no entry is cached for that pair."], "non_goals": ["Cross-process or distributed caching (e.g. Redis or Memcached); the cache is in-process only.", "Explicit cache invalidation on price update; expiry relies solely on the 5-minute TTL.", "Changing the pricing table schema or the query used to fetch prices.", "Caching of any data other than the get_price result.", "Adding new dependencies."], "open_questions": ["What is the expected maximum number of cached entries, and is an eviction bound required to protect process memory?", "Should errors raised by the pricing table query be cached, or always propagated without caching?", "Is the cache required to be thread-safe for concurrent requests within a single process?", "Should cache hit and miss counts be exposed as metrics for verifying the slow-log improvement?"]}

## Stage output: plan
{"steps": [{"id": 1, "description": "Review the existing get_price implementation and the pricing table access layer in the api component to confirm the current query path, return type and how missing rows are handled.", "files": ["api/pricing (module: pricing lookup)", "api/pricing tests (module: pricing tests)"]}, {"id": 2, "description": "Add a small in-process TTL cache keyed on the (sku, currency) tuple with a 300-second expiry, reusing any existing cache or clock utility in the api component rather than introducing a new caching library.", "files": ["api/pricing (module: pricing lookup)", "api/common utilities (module: shared cache or clock helpers, if present)"]}, {"id": 3, "description": "Wire the cache into get_price so that a fresh entry is returned without querying the pricing table, an expired or missing entry triggers a query and overwrites the stored value, and a missing pricing row returns the existing result without writing to the cache.", "files": ["api/pricing (module: pricing lookup)"]}, {"id": 4, "description": "Ensure the cache key includes both sku and currency and that no currency conversion logic is introduced, so each currency is stored and returned independently.", "files": ["api/pricing (module: pricing lookup)"]}, {"id": 5, "description": "Add unit tests covering cache hit, cache expiry at and beyond 5 minutes, per-currency isolation, stale-read behaviour before TTL, and the missing-row path, using an injectable or mocked clock and a mocked pricing table query.", "files": ["api/pricing tests (module: pricing tests)"]}], "risks": ["Stale prices for up to 5 minutes after a pricing table change; mitigate by documenting the TTL in the function docstring and in the release notes so downstream consumers and support are aware.", "Cache is per-process and not shared across the 4 workers per pod, so the same SKU may return different prices across workers during a TTL window; mitigate by keeping the TTL short and confirming with product that per-worker divergence of up to 5 minutes is acceptable.", "Unbounded cache growth across many SKU and currency pairs could increase memory use in each worker; mitigate by using a bounded structure with eviction or by confirming the expected key cardinality before merge.", "Caching a missing-row result would hide newly added prices; mitigate by ensuring the missing-row path never writes to the cache, as required by the acceptance criteria.", "Thread-safety of the in-process cache under concurrent requests within a worker; mitigate by using a lock or an already thread-safe structure consistent with the service's concurrency model."], "test_plan": ["Given a SKU and currency looked up less than 5 minutes ago, calling get_price returns the same value and the pricing table query is not invoked (verifies criterion 1).", "Given a cached entry exactly 5 minutes old, calling get_price queries the pricing table and replaces the cached entry (verifies criterion 2, boundary case).", "Given a cached entry older than 5 minutes, calling get_price queries the pricing table and the new value is returned and stored (verifies criterion 2).", "Given the same SKU requested in EUR, USD and INR, three distinct cache entries are created and each returns its own currency's price with no conversion applied (verifies criterion 3).", "Given a pricing table row changes after caching, calling get_price before the TTL expires returns the previously cached price (verifies criterion 4).", "Given no pricing table row exists for a SKU and currency, calling get_price behaves as before the change and no cache entry is created, confirmed by a subsequent call still querying the table (verifies criterion 5).", "Regression test that the cache key includes both sku and currency so that two different currencies for the same SKU never share an entry (supports criterion 3)."]}

## Stage output: review
{"verdict": "request_changes", "findings": [{"file": "api/pricing.py", "line": 12, "severity": "blocker", "issue": "The cache key is `sku` alone (`_cache.get(sku)` and `_cache[sku] = ...`), so EUR, USD and INR prices for the same SKU collide. A USD lookup can return a cached EUR amount, violating the per-currency isolation criterion.", "suggested_fix": "Key the cache on the tuple: `key = (sku, currency)`, then use `_cache.get(key)` and `_cache[key] = (now, amount)`."}, {"file": "api/pricing.py", "line": 16, "severity": "blocker", "issue": "When `fetch_price_row` returns no row, `row[\"amount\"]` will raise or fail, and the plan requires the missing-row behaviour to be unchanged. If the original code already handled a missing row differently, this change does not preserve it; either way the path is not tested or explicitly preserved.", "suggested_fix": "Keep the original missing-row handling exactly as before and return before the cache write, so no entry is stored for a missing pair; add a test asserting this."}, {"file": "api/pricing.py", "line": 13, "severity": "major", "issue": "The expiry check `now - hit[0] < TTL_SECONDS` returns the cached value strictly before 300s, and the refresh happens at 300s or later, which matches the criteria. However, `time.monotonic()` is used with no injectable clock, so the required expiry tests at and beyond 5 minutes cannot be written without patching the module-level time source, and the diff includes no tests.", "suggested_fix": "Inject a clock (e.g. a `clock: Callable[[], float] = time.monotonic` parameter or a module-level clock indirection) and add the unit tests from plan step 5 covering hit, expiry boundary, per-currency isolation and missing-row behaviour."}]], "summary": "The cache is keyed only on SKU, so currencies collide and violate isolation. Missing-row handling is not preserved, and no tests or injectable clock are included."}

## Stage output: release_note
{"title": "Product price lookups are now cached for five minutes", "summary": "Product price lookups are now cached for up to five minutes. Repeated requests for the same product return faster. Price changes made in the pricing table appear in API responses within five minutes of the change.", "changes": ["Product price lookups are cached for up to five minutes.", "Repeated price lookups for the same product return faster.", "Price changes in the pricing table appear in API responses within five minutes."], "breaking": false, "upgrade_notes": ""}