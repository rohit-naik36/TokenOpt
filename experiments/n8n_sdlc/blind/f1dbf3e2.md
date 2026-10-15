## Ticket
{
  "id": "T01",
  "title": "Add pagination to GET /v1/invoices",
  "type": "feature",
  "priority_hint": "High",
  "reporter": "support-lead",
  "labels": [
    "api",
    "invoices",
    "customer-escalation"
  ],
  "description": "The invoices list endpoint returns every invoice for an account in one response. Two large customers (more than 20,000 invoices each) now time out in the dashboard and in their nightly sync jobs. Please add page-based pagination.\n\nRequested behaviour: query parameters `page` (1-based, default 1) and `page_size` (default 50, maximum 200; larger values are clamped to 200). The response keeps the current `invoices` array and adds `page`, `page_size` and `total`. A page beyond the last returns an empty `invoices` array with HTTP 200, not an error. Ordering must stay newest first by `created_at`.",
  "environment": "Python 3.12, FastAPI, PostgreSQL 15, SQLAlchemy 2.0. Service: api.",
  "comments": [
    "support-lead: Acme Corp's sync job has failed three nights running with a gateway timeout.",
    "backend-dev: We already have a `paginate()` helper in `api/utils.py` for the orders endpoint but it returns cursors, not pages, so I will not reuse it.",
    "pm: Dashboard team needs `total` to render page numbers."
  ]
}

## Diff
diff --git a/api/routes/invoices.py b/api/routes/invoices.py
--- a/api/routes/invoices.py
+++ b/api/routes/invoices.py
@@ -1,22 +1,34 @@
 from fastapi import APIRouter, Depends, Query
-from sqlalchemy import select
+from sqlalchemy import func, select
 from sqlalchemy.orm import Session

 from api.db import get_session
 from api.models import Invoice
 from api.schemas import InvoiceOut

 router = APIRouter()

+MAX_PAGE_SIZE = 200
+

 @router.get("/v1/invoices")
-def list_invoices(account_id: int, db: Session = Depends(get_session)):
-    rows = db.execute(
-        select(Invoice).where(Invoice.account_id == account_id).order_by(Invoice.created_at.desc())
-    ).scalars().all()
-    return {"invoices": [InvoiceOut.model_validate(r) for r in rows]}
+def list_invoices(
+    account_id: int,
+    page: int = Query(1, ge=1),
+    page_size: int = Query(50, ge=1),
+    db: Session = Depends(get_session),
+):
+    page_size = min(page_size, MAX_PAGE_SIZE)
+    offset = page * page_size
+    base = select(Invoice).where(Invoice.account_id == account_id)
+    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
+    rows = db.execute(
+        base.order_by(Invoice.created_at.desc()).offset(offset).limit(page_size)
+    ).scalars().all()
+    return {
+        "invoices": [InvoiceOut.model_validate(r) for r in rows],
+        "page": page,
+        "page_size": page_size,
+        "total": total,
+    }


## Stage output: triage
{"severity": "P1", "category": "feature", "component": "api", "summary": "Add pagination (page/page_size params) to GET /v1/invoices to prevent timeouts for accounts with large invoice counts.", "risk_flags": ["customer-escalation", "gateway-timeout"], "needs_security_review": false}

## Stage output: requirements
{"user_story": "As a dashboard user or sync job, I want to retrieve invoices in manageable chunks so that requests do not time out on accounts with large invoice volumes.", "acceptance_criteria": ["Given no query parameters are provided, When the GET /v1/invoices endpoint is called, Then it returns page 1 with a default page_size of 50 and HTTP status 200.", "Given the page parameter is set to an integer greater than zero, When the request is made, Then the response includes the requested page of invoices ordered newest first by created_at.", "Given the page_size parameter exceeds 200, When the request is made, Then the value is clamped to 200 and the response returns exactly 200 items per page.", "Given a page number that exceeds the total number of available pages, When the request is made, Then the response contains an empty invoices array with HTTP status 200.", "Given valid pagination parameters are provided, When the request is made, Then the response includes integer values for page, page_size, and total count.", "Given a GET /v1/invoices request with valid pagination, When the response is received, Then the ordering of the invoices array remains newest first by created_at."], "non_goals": ["The existing paginate() helper in api/utils.py will not be reused for this implementation.", "Cursor-based pagination will not be implemented for this endpoint."], "open_questions": []}

## Stage output: plan
{"steps":[{"id":1,"description":"Update GET /v1/invoices route to parse query parameters page and page_size with defaults 1 and 50 respectively, clamping page_size to max 200","files":["api/routes/invoices.py"]},{"id":2,"description":"Modify the database query logic to apply LIMIT and OFFSET based on parsed page and page_size while maintaining newest-first ordering by created_at","files":["api/routes/invoices.py"]},{"id":3,"description":"Construct response dictionary including invoices array, calculated page number, applied page_size, and total count of all invoices","files":["api/routes/invoices.py"]},{"id":4,"description":"Implement logic to return empty invoices array with HTTP 200 when requested page exceeds available pages","files":["api/routes/invoices.py"]},{"id":5,"description":"Add unit tests covering default parameters, parameter clamping, out-of-range pages, and ordering verification","files":["tests/api/test_invoices_pagination.py"]],"risks":["Existing SQLAlchemy query might not support large OFFSET values efficiently; mitigate by ensuring database index exists on created_at column if not already present.","Response payload size increases with total count field; ensure no memory issues occur when calculating total for very large datasets (handled by separate COUNT query or cached metadata)."],"test_plan":["Verify GET /v1/invoices returns page=1, page_size=50, total=N without query params.","Verify GET /v1/invoices?page=2&page_size=50 returns correct slice and updated pagination metadata.","Verify GET /v1/invoices?page_size=300 clamps to 200 and returns exactly 200 items.","Verify GET /v1/invoices?page=99999 returns empty invoices array with HTTP 200.","Verify response includes integer fields for page, page_size, and total.","Verify invoice ordering is strictly descending by created_at across all pages."]

## Stage output: review
{"verdict":"request_changes","findings":[{"file":"api/routes/invoices.py","line":17,"severity":"blocker","issue":"The query uses `offset(offset)` where `offset = page * page_size`. For large datasets (e.g., page=10, page_size=200), this creates a massive OFFSET that PostgreSQL cannot efficiently execute without an index on the ordering column. The ticket explicitly warns about this risk but the implementation does not verify or enforce an index on `created_at` before relying on OFFSET.","suggested_fix":"Add logic to check for an index on `Invoice.created_at` and raise a 500 error or fallback to cursor-based pagination if missing, OR use a more efficient pattern like partitioning or subqueries. Alternatively, document the requirement for the DBA team to add the index before deployment."},{"file":"api/routes/invoices.py","line":17,"severity":"major","issue":"The implementation calculates `total` using `select(func.count()).select_from(base.subquery())`. While this avoids scanning the full table for each row, it still issues a separate COUNT query per request. For very large datasets, this can be slow. The ticket mentions handling memory issues but does not address the latency impact of multiple queries.","suggested_fix":"Consider caching the total count or using a single query with `COUNT(*)` and `LIMIT/OFFSET` if supported by the database version, or accept the trade-off and document it."},{"file":"api/routes/invoices.py","line":17,"severity":"minor","issue":"The implementation does not handle the case where `page` is provided as a non-integer (e.g., string) due to FastAPI's default behavior. While `Query(1, ge=1)` enforces constraints, it does not explicitly validate that the input is an integer.","suggested_fix":"Add explicit type validation using `Query(..., alias="page", ...)` or use a custom validator to ensure `page` is an integer."}],"summary":"The implementation risks performance issues with large OFFSET values and lacks robustness for non-integer inputs. An index on created_at is required but not verified."}

## Stage output: release_note
{"title": "Pagination added to GET /v1/invoices", "summary": "Added page and page_size query parameters to the invoices list endpoint. Responses now include pagination metadata fields.", "changes": ["The GET /v1/invoices endpoint now accepts page and page_size query parameters.", "Responses include new integer fields: page, page_size, and total.", "Requests for pages beyond the available data return an empty invoices array with HTTP 200."], "breaking": false, "upgrade_notes": ""}