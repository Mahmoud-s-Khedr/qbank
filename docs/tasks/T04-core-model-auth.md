# T04 — Core data model, auth, org scoping, users and taxonomy APIs

**Owner:** Codex · **Branch:** `task/T04` · **Refs:** SPEC §1, §3 (Security), F5.2, F8.1 · ARCHITECTURE §2 (API conventions), §3 · AGENTS.md

## Goal
The multi-tenant foundation every later feature builds on: organizations, users, roles, cookie auth with CSRF,
org-scoped data access, and the subject → chapter → lesson taxonomy.

## Scope
`backend/**` only. Create only these tables now: `organizations`, `users`, `subjects`, `chapters`, `lessons`.
Every other table in ARCHITECTURE §3 belongs to a later task. Do not create it.

## Existing code to build on (from T01)
- `backend/src/qbank/db/__init__.py`: `Base`, `UUIDPk`, `Timestamps`, `get_db`
- `backend/src/qbank/api/main.py`: `create_app`, `problem()`, exception handlers, the health route
- `backend/src/qbank/config.py`: `Settings`
- `backend/tests/conftest.py`: the `app`, `client` and `database` fixtures

You may restructure `api/main.py` into `api/routers/*` as ARCHITECTURE §2 describes. Keep the health contract identical.

## Requirements

### Models (`qbank/models/`) + one Alembic migration
- `Organization`: name, `settings` JSONB (default `{}`).
- `User`: org_id FK, email (unique, stored lowercased), name, password_hash, role enum (`admin`/`editor`/`teacher`), is_active, last_login_at.
- `Subject`: org_id, name, language enum (`ar`/`en`), grade (nullable str). Unique (org_id, name, grade).
- `Chapter`: subject_id FK (cascade), title, position int. `Lesson`: chapter_id FK (cascade), title, position int.
- Use PostgreSQL native enums via SQLAlchemy `Enum(..., name=...)`. `alembic check` must stay clean.

### Auth (`qbank/auth/` or `qbank/services/auth.py`)
- argon2-cffi password hashing, with a transparent rehash on login if the parameters changed.
- PyJWT HS256 session token: claims `sub` (user id), `org`, `role`, `exp` (configurable, default 12h), `iat`, `jti`.
- `POST /api/v1/auth/login` `{email, password}` sets two cookies:
  - `qbank_session` = JWT: httpOnly, SameSite=Lax, Path=/, Secure when `settings.cookie_secure`.
  - `qbank_csrf` = a random 32-byte urlsafe token: **not** httpOnly (the SPA reads it), same other attributes.
  It returns `UserOut`. Wrong credentials and inactive users both get the same 401 problem (`code: invalid_credentials`).
- `POST /api/v1/auth/logout` clears both cookies. `GET /api/v1/auth/me` returns `UserOut`, or 401.
- **CSRF**: middleware or dependency. For POST/PUT/PATCH/DELETE requests carrying a `qbank_session` cookie, require the
  header `X-CSRF-Token` to equal the `qbank_csrf` cookie (constant-time compare). Otherwise 403 `code: csrf_failed`. `/auth/login` is exempt.
- Dependencies in `api/deps.py`: `current_user` (401 if missing/invalid/expired/inactive), and `require_role(*roles)` (403 `code: forbidden`).
- Settings additions: `cookie_secure: bool` (default False in dev), `session_ttl_minutes`. Validation: when `env == "prod"`,
  `jwt_secret` must not be the dev default and must be at least 32 characters, and `cookie_secure` must be true. Fail fast at startup.

### Org scoping
- Every service function takes `org_id: UUID` explicitly. A helper `scoped(stmt, Model, org_id)` adds the org filter.
  For chapters and lessons, scoping goes through the parent subject.
- Accessing another org's resource returns **404**, not 403, so existence never leaks.

### APIs (thin routers → `qbank/services/`)
- Users (admin only): `GET /api/v1/users`, `POST /api/v1/users` (create with an initial password, role), `PATCH /api/v1/users/{id}` (name, role, is_active). An admin cannot demote or deactivate themselves.
- Taxonomy (read: any role; write: admin/editor):
  - `GET/POST /api/v1/subjects`, `GET/PATCH/DELETE /api/v1/subjects/{id}`
  - `GET /api/v1/subjects/{id}/tree` → the subject with nested chapters → lessons, ordered by position
  - `POST /api/v1/subjects/{id}/chapters`, `PATCH/DELETE /api/v1/chapters/{id}`
  - `POST /api/v1/chapters/{id}/lessons`, `PATCH/DELETE /api/v1/lessons/{id}`
  - `POST /api/v1/subjects/{id}/chapters/reorder` `{ids: [...]}` and `POST /api/v1/chapters/{id}/lessons/reorder` `{ids: [...]}`. The ids must be exactly the current set, otherwise 422.
  - `PATCH /api/v1/lessons/{id}` accepts `chapter_id` to move a lesson (same subject only). It is appended at the end.
  - Deleting a non-empty subject or chapter returns 409 `code: not_empty`. Later tasks will extend "non-empty" to cover questions. Put the check in one service function, `ensure_deletable_*`.
- List endpoints use cursor pagination `{items, next_cursor}` via a generic helper in `qbank/api/pagination.py` (keyset on `(created_at, id)`). The helper is reused by later tasks, so make it generic and typed.
- All errors are problem+json with a stable `code`.

### CLI (`python -m qbank.cli`, argparse; no new deps)
- `create-admin --org NAME --email E --password P [--name N]`
- `seed-dev`: idempotent. It creates org "Demo School / مدرسة تجريبية" and the users `admin@demo.local`, `editor@demo.local` and `teacher@demo.local` (password `demo1234`, refused when env=prod). It also creates the subjects اللغة العربية (ar, grade "3 ثانوي") and Biology / الأحياء (ar, grade "3 ثانوي"), each with 2 chapters × 2 lessons.

### Tests (integration against the `database` fixture, plus unit tests where possible)
- Login success, wrong password, inactive user, expired token, logout, `/auth/me`.
- CSRF: an unsafe request with the session cookie but no/wrong header → 403. Correct header → OK. Login exempt.
- Roles: a teacher cannot create a subject (403). An editor cannot manage users (403).
- **Org isolation**: a user in org B gets 404 on org A's subject, chapter, lesson and user, and list endpoints never include org A's rows.
- Taxonomy: CRUD, tree ordering, reorder validation, moving a lesson, 409 on a non-empty delete.
- Pagination helper: stable ordering across pages, plus the empty and last-page cases.
- Prod settings validation fails with the default secret.
- Keep coverage ≥ 80%.

### Housekeeping
- New deps: argon2-cffi, pyjwt. Nothing else without justification.
- `make api-gen` → commit `backend/openapi.json`. (`frontend/` may not exist on your branch. That's fine, because the Makefile skips it.)
- Add the new vars to `.env.example`.

## Acceptance
`make infra-up && make be-install && make check` passes. `python -m qbank.cli seed-dev` works twice in a row.
A manual curl flow works: login → GET subjects → POST subject with the CSRF header.
