## What and why

<!-- What changed and why, in a few sentences. Bullet the notable changes
if there are several. -->

closes #

## Contract and sync impact

<!-- API: OpenAPI changes (routes, schemas, fields), changes to the nested
`GET /trips` shape, status code changes. UI: the API branch or PR this
depends on, whether a new edit is offline-capable or online-only.
Write "None" if neither applies. -->

## Testing

<!-- New or changed tests, and anything checked by hand. -->

## Checklist

- [ ] Branch is `ba-<n>-<slug>` from `develop` and the issue's acceptance criteria are met
- [ ] Changes follow `api` → `services` → `models` layering
- [ ] PATCH schemas subclass `UpdateSchema`, NOT NULL fields are in `non_nullable`, and services apply them with `save_updates()`
- [ ] Model changes regenerate the single initial migration (no new migration file) and `alembic check` passes
- [ ] Trip and gear routes enforce ownership (missing or unowned → 404); `shared.py` stays read-only and token-scoped
- [ ] Tests added in `tests/`; `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy .` pass
- [ ] OpenAPI changes are listed above so the UI can regenerate `schema.d.ts`
