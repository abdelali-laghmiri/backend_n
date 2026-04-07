# Performance Audit

## Scope

This audit covers application-level performance and scalability characteristics, not just the `performance` business module.

## Runtime Characteristics

The project is designed as a synchronous-request modular backend with a small amount of websocket push behavior. Most read models are generated live from operational tables.

## Query and Data-Access Audit

### Positive Observations

- Monthly attendance reports aggregate from daily summaries instead of recomputing only from raw scans.
- Dashboard endpoints use database aggregation functions rather than moving all work into Python.
- Single-record lookups often use bounded queries.

### Confirmed Findings

- No caching layer was found for dashboard summaries or other aggregate-heavy endpoints.
- No shared query abstraction exists, so optimization opportunities are scattered across service code.
- Many list-style surfaces are not paginated in the API layer.
- Admin list screens rely on hardcoded limits such as 200 or 300 rather than real pagination.

## Scalability Audit

### Confirmed Findings

- Notification websocket delivery is single-process and in-memory.
- Attendance raw scan events have no visible retention strategy.
- Several services are large enough that performance tuning will be harder because data access and business logic are tightly mixed.

### Likely Risks

- Dashboard and request-summary endpoints may become heavier as data volume grows.
- Manual repeated lookups in scope and hierarchy logic may create avoidable query overhead.
- Fixed-result admin screens may become slow or incomplete when operational datasets outgrow the chosen caps.

## Performance Audit by Area

### Dashboard

- Live aggregation is simple and correct for small to medium datasets.
- It is a likely future hotspot because it joins multiple operational domains with no cache.

### Requests

- The workflow engine is feature-rich, but large service methods make query behavior harder to reason about quickly.

### Attendance

- The split between raw scans, daily summaries, and monthly reports is a good foundation.
- Lack of retention policy will turn raw scan storage into a long-term cost center.

### Admin Panel

- Server-rendered pages avoid a heavy frontend bundle.
- Large controller logic and capped list queries are a maintainability and scalability compromise, not a long-term solution.

## Performance Audit Conclusion

The current architecture is likely acceptable for early-stage or moderate internal usage. The main performance concern is future scale: the code favors directness over reusable read models, caching, and large-data ergonomics.

## Recommended Performance Priorities

1. Add pagination to large list endpoints and admin pages.
2. Add retention/archival rules for attendance raw events.
3. Introduce cache or pre-aggregated read models for dashboard hotspots if usage increases.
4. Refactor the largest services so profiling and targeted optimization become easier.
