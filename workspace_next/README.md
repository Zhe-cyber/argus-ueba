# Inactive analyst workspace implementation

This package holds the next case workspace outside `backend/`: the collecting
pilot pins the complete backend Python file set. Adding an unmounted backend
module would still change that set. Do not move these files or register this
router in the live application during collection without a reviewed release.

`case_store.py` reuses the event store transaction and database backend. It has
no initialization side effects. Call `init_db()` explicitly on a **copy** before
mounting `case_api.router` in an isolated FastAPI application.

This is a staged foundation, not a deployed case system. Existing live
investigation writers still operate unchanged. There must be a deliberate
writer switch at cutover; these are not two competing live writable stores.

The API supports case create/read/list/edit, explicit account/finding/event
links and normalized event evidence. Writes require a request key and actor;
edits/links also require the current case version. Actor is an analyst-supplied
label, not authenticated identity. No response automation or model activation.

PostgreSQL-compatible statements are present but only SQLite has been tested.
Person-mapping snapshots, source-filtered case timelines, finding search and
frontend pages are now exercised in an isolated preview. Live navigation,
writer cutover and deployment remain subsequent deliverables. Account links
mean analyst-selected related entities, not approved ownership. See
`docs/CASE_WORKSPACE_PREVIEW_2026-10-30.md` for current verification and limits.
