# Backend

FastAPI service for the library catalog and circulation system. In production it also serves
the built frontend from the same origin.

## Run locally

```bash
uv sync
cp .env.example .env          # optional, every setting has a local default
uv run alembic upgrade head   # needs PostgreSQL at DATABASE_URL
uv run python -m app.seed     # demo library and demo accounts (skipped if books or members exist)
uv run python -m app.seed --reset   # replace the library data; refused in production
# options: --seed N (default fixed), --today YYYY-MM-DD (default today, UTC), --years N (default 3)
uv run uvicorn app.main:create_app --factory --reload --port 8000 --no-access-log
```

The app writes its own access log line (with the request id), so uvicorn's is turned off.

- API: `http://localhost:8000/api/health`, interactive docs at `/api/docs` (off in production).
- Web app: served from `FRONTEND_DIST_DIR` once the frontend is built; otherwise `/` explains
  that it is missing.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest                  # integration tests skip when the database is unreachable
REQUIRE_DB=1 uv run pytest     # fail instead of skip (use in CI)
```

Integration tests never touch the development database. They use `TEST_DATABASE_URL`, or
`DATABASE_URL` with `_test` appended to the database name, which they create and migrate themselves.

## Settings

| Variable                    | Default                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| `APP_ENV`                   | `local` (`local`, `test` or `production`)                               |
| `DATABASE_URL`              | `postgresql+asyncpg://library:library@127.0.0.1:55432/library`          |
| `LOG_LEVEL`                 | `INFO`                                                                  |
| `FRONTEND_DIST_DIR`         | `../frontend/dist` relative to this folder                              |
| `SESSION_SECRET`            | a dev-only value; production requires 32+ random characters             |
| `LOAN_PERIOD_DAYS`          | `14`: days until a new loan is due (1 to 90)                            |
| `PUBLIC_BASE_URL`           | `http://localhost:8000`: the address browsers use                       |
| `DEMO_LOGIN_ENABLED`        | `true`, except `false` when `APP_ENV` is `production`                   |
| `GOOGLE_CLIENT_ID`          | unset; Google sign-in shows when this and the secret are set            |
| `GOOGLE_CLIENT_SECRET`      | unset                                                                   |
| `STAFF_EMAILS`              | empty; comma-separated addresses that join as staff                     |
| `SESSION_IDLE_MINUTES`      | `720`: a session ends after this long without a request                 |
| `SESSION_MAX_HOURS`         | `168`: a session ends this long after sign-in, whatever happens         |
| `ALLOWED_ORIGINS`           | `PUBLIC_BASE_URL`, plus `http://localhost:5173` outside production      |
| `OPENROUTER_API_KEY`        | unset; the Copilot shows as unavailable without it                      |
| `OPENROUTER_BASE_URL`       | `https://openrouter.ai/api/v1`                                          |
| `COPILOT_MODEL`             | `google/gemini-3.8-flash`                                               |
| `COPILOT_TIMEOUT_SECONDS`   | `45`: one whole turn, every model call and lookup together              |
| `COPILOT_MAX_TOOL_ROUNDS`   | `6`: rounds of lookups per turn                                         |
| `COPILOT_MAX_OUTPUT_TOKENS` | `2000` per model call                                                   |
| `COPILOT_RATE_PER_MINUTE`   | `20` messages per user                                                  |
| `COPILOT_FAKE_MODEL`        | `false`; `true` answers with an offline stand-in, refused in production |
| `ISBN_LOOKUP_ENABLED`       | `true`: the add-book form asks Open Library; `false` answers 503        |

## Sign-in

Every endpoint except health, `/api/auth/config`, demo sign-in, sign-out and the Google routes
needs a signed-in user; staff-only endpoints answer members with 403. A session is a random token
in an HttpOnly, SameSite=Lax cookie named `session` (Secure in production); the database keeps
only its SHA-256 hash. POST, PUT, PATCH and DELETE requests whose `Origin` is not in
`ALLOWED_ORIGINS` are refused with 403 `origin_not_allowed`.

- **Demo sign-in**: `POST /api/auth/demo {"role": "staff" | "member"}` signs in as Demo Staff or
  the demo member. After `python -m app.seed` the demo member signs in as the seeded Maya Hassan,
  so My loans and History have data.
- **Google sign-in**: create an OAuth client of type "Web application" in Google Cloud, add
  `PUBLIC_BASE_URL/api/auth/google/callback` as an authorized redirect URI, then set
  `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. New people join as members, or as staff when
  their address is in `STAFF_EMAILS`.

## Copilot

`GET /api/copilot/config` says whether the assistant is available and which face the signed-in
user gets (members: catalog search, categories, a book without borrowers, and their own loans;
staff: the same with borrowers shown, plus member, loan, overdue and copy lookups, borrow and
return as proposals the user confirms, and the analyst's metric queries and forecasts).
`POST /api/copilot/chat
{"message", "conversation_id"?}` answers with `text/event-stream`: `conversation`, then `status`
and `result` while lookups run, then `message` or `error`, and `done` last. Without a key it
answers 503 `copilot_unavailable` before any stream, and every other page works as usual.

- The model is reached through OpenRouter's OpenAI-compatible API with httpx; any model whose
  parameters include tools works through `COPILOT_MODEL`.
- Every number in a reply must appear in a lookup result or the user's own words. A reply that
  fails gets one corrective retry, then the lookup results are shown as plain text instead.
- Conversations are stored per user; the model gets the latest 20 messages as context.
- The per-user rate limit is counted in memory by each process.
- `COPILOT_FAKE_MODEL=true` runs the Copilot offline for development: it searches the catalog for
  the words of the message, or reads the member's loans, and says it found something.
