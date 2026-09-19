---
title: The build, step by step - what was agreed, what was built, how it was verified, and what went wrong
status: verified
as_of: 2026-09-20
last_verified: 2026-09-20
verification_method: Written at the end of each step from that step's work: the outputs of the verification gate run at each step, browser walks of each step's checklist against the Docker stack, and live Copilot turns recorded with curl
scope: Steps 0 to 7 of the delivery order in the product spec, all built on 2026-09-19, and the checks made on 2026-09-20 before publishing. Step 8 was left unbuilt by the owner and is named only in the last section
confidence: High. Every number below was read from a command's output on the day it was measured
known_gaps: Timings were measured once on one development machine, and the live figures once on the deployed one. Nothing here is measured under real traffic: the deployment of 2026-09-20 has had no users but its owner. CI ran for the first time on 2026-09-20 and passes on the submitted commit
reverify_when: A step is added, or a number quoted here is re-measured
---

# Build log

The product was defined before any code (`../10-product/product-spec.md`), then built in the value
order of that spec's section 4 (D-14): every step ends runnable, tested and documented, so the work
could stop after any of them and still be submitted. Each step followed the same loop, described in
`../40-method/how-this-was-built.md`: an agreed brief with an outcome checklist, a build, then an
integration pass that ran the full gate and walked every checklist line in a browser.

## Step 0 · Foundation

**Agreed:** one repository holding the application (`repo/`), the AI working harness (`.claude/`)
and this knowledge base (D-16); FastAPI and PostgreSQL with the React app served from the same
container (D-04); demo posture (D-17); no separate code-review stage (D-15).

**Built:**
- The working harness: rules, skills, four hooks and their self-tests, set up so a step is done
  when the checks are green and the app has been walked.
- The knowledge base with the product spec and the first 17 decisions.
- The API skeleton: settings that refuse weak secrets in production, one error envelope, request
  ids, security headers, an access log, async SQLAlchemy with an Alembic baseline, a health check
  that probes the database, and serving of the built web app.
- The web app shell with light and dark themes, the navigation for both roles, and a live API
  status indicator.
- One Docker image, a compose stack (Postgres, a one-shot migration, the app), a CI workflow, and
  `verify.project.sh` behind `verify.sh --full`. The database is published on
  `127.0.0.1:55432` (set `DB_PORT` to change it), away from the default port, so it cannot collide
  with a PostgreSQL already listening there.

**Verified:** the harness self-tests passed (219 hook cases and 71 knowledge-check cases, 0
failures). The gate passed 23 of 23. A lint error planted on purpose made the gate fail
with exit 1, so its green is meaningful. In the browser the shell showed "API ok" with no console
errors, served by the container.

**What went wrong, and the fix:** the health check timed out against a healthy database.
Measured: connecting through `localhost` took 2.12 s against 0.06 s through `127.0.0.1`, because
`localhost` tries IPv6 first and the port is published on IPv4 only. The default address became
`127.0.0.1`, and the trap is recorded in the harness rule `.claude/rules/working-here.md`.

## Step 1 · The assignment's core

**Agreed:** C01 to C08 on the full data model (books, copies, members, loans, activity), search by
trigram matching (D-18), one active loan per copy enforced by the database (D-12).

**Built:** migration 0002, a service layer holding every rule, the books, members, loans and
activity endpoints, and a small development seed; the catalog with URL-bound
search, add and edit forms whose validation mirrors the server's, the book page with Borrow,
Return, Add copy and a delete dialog that says whether the book will be deleted or archived,
members and activity.

**Verified:** 198 backend tests and 60 frontend tests. An integration test races two real
database connections borrowing the same copy and gets exactly one loan and one 409; it passed five
runs in a row. The browser walk covered all seven checklist lines: availability badges; a book
added with two copies; an ISBN with a wrong check digit rejected with a precise message; borrow
and return with confirmations; archive offered for a book with history and refused for a book with
a copy on loan; "herb" finding both Frank Herbert books and "978-0547" finding The Hobbit; every
action recorded in the activity history.

**What went wrong, and the fix:** the tests shared the development database, and because database
sequences never roll back, copy codes in the demo data had drifted to CP-1103. Integration tests
now create, migrate and use their own `library_test` database; a before-and-after reading of the
development sequence (1104 and 1104) proved it untouched.

## Step 2 · Sign-in, roles, member self-service

**Agreed:** demo sign-in for each role so a reviewer can try both, Google sign-in, server-side
sessions, the two roles enforced on the server, and pages for members (D-02, D-05).

**Built:** users and sessions (migration 0003); demo sign-in; Google sign-in through OpenID Connect
with PKCE; opaque session tokens stored only as SHA-256 hashes with 12-hour idle and 7-day absolute
expiry; an Origin check on state-changing requests; staff-only endpoints; a member view of books
without borrower names; `/api/me/loans`; the acting user on every activity event.
The sign-in page, role-aware navigation, an account menu, My loans and History.

**Verified:** 367 backend tests, including a permission matrix over every endpoint for anonymous,
member and staff users, and 103 frontend tests. The browser walk signed in as each role, checked
the member menu, the "not available for your role" page, My loans, sign-out and staff sign-in.

**What went wrong, and the fix:** in the walk, signing out failed with "this request came from a
site that is not allowed". The Origin check trusted only the configured address (`localhost`),
and the app had been opened at `127.0.0.1`, so the app's own requests were refused. A reviewer
opening the IP address would have hit it. The check now always trusts the server's own origin (its
scheme and Host header, which a foreign page cannot forge) as well as the configured list. A
regression test was written, shown to fail without the fix, and to pass with it.

## Step 3 · Operations and the demo library

**Agreed:** a generated library from reader personas, without planted patterns or an answer key
(D-10, revised at the owner's request); the dashboard, overdue tracking, a circulation desk, member
detail and book loan history.

**Built:** the generator: 286 real titles in 14 categories, 7 reader personas (student, software
professional, retiree, parent, casual reader, book-club member, teen reader), 200 members joining
over three years, and day-by-day borrowing against real copy availability. The
dashboard in four queries, the loans list with status filters and search, copy lookup that accepts
`CP-0012`, `cp-12` or `12`, and member detail. The dashboard, a circulation desk
whose code box stays focused for scanning, member pages and book loan history.

**Verified:** the generator ran inside the Docker image in 2.1 s and produced 484 copies, 5,482
loans, 120 on loan and 6 overdue for seed 1 on 2026-09-19; the same seed and date gave identical
rows. The personas show through without being planted: technology's share of loans grew from 1.7%
(2023) to 7.4% (2026) as software professionals joined, children's loans peak in summer and
December, study-heavy categories dip in July and August, and 20.2% of returns were late. Query
plans on 30,000 loans showed the existing indexes suffice (active and overdue lists under 1 ms), so
no index migration was added. The browser walk: the dashboard (286 titles, 120 on loan, 6 overdue,
122 members active in 90 days); the desk found copy 74 by number and returned a loan 50 days
overdue, leaving the box empty and focused; a member with 107 past loans; a book with 56 loans in
its history. 451 backend and 135 frontend tests.

**What went wrong, and the fix:** the builder wrote the catalog's ISBNs from memory. All pass the
checksum, but a valid checksum does not prove a number belongs to that book. It matters only when
covers are shown, so it is an open item for step 7 (`../99-pending.md`).

## Step 4 · The Copilot and its member face

**Agreed:** one AI module with role-scoped faces (D-06), the safety rules as product rules (D-07),
models reached through OpenRouter (D-11), the member face first.

**Built:** the engine: an OpenRouter client with one 45-second deadline per turn and one retry
that honours Retry-After; a typed tool registry whose parameters reject unknown fields and never
carry an identity; up to six tool rounds; a check that every number in a reply appears in a lookup
result or the user's words, with one corrective retry and then a plain rendering of the results;
conversations stored per user and face (migration 0004); answers streamed as server-sent events;
logs that record each turn without message text; a scripted fake model for tests that production
refuses to enable. The panel, with product components inside the conversation. The default model, `google/gemini-3.8-flash`, was chosen from OpenRouter's public
list of 447 models, 378 of them with tool support (D-19).

**Verified:** 523 backend and 160 frontend tests, all against the fake model. Then live, with the
real model:

| Asked (as the demo member) | What happened |
|---|---|
| "Show me available science fiction" | looked up the categories, searched available science fiction, showed 5 books as cards; 6.3 s |
| "Can I borrow Dune?" (follow-up) | resolved Dune from the conversation: 3 of 3 available; said borrowing happens at the desk |
| "When are my books due? Anything overdue?" | the member's own two loans, one overdue by 4 days, correct against the data |
| "Reserve the next copy of Homo Deus and renew my other book" | declined both, named what the product does offer |

In the panel, signed in as staff, "Which copies of The Hobbit are out, and who has them?" returned
the book, its copies and the borrower's name, which staff may see and members never receive.

**What went wrong:** nothing blocking. The walk found two polish items carried into step 5: a book
shown twice when the Copilot searches and then opens it, and dates written in ISO form.

## Step 5 · The staff face: lookups, and Borrow and Return that staff confirm

**Agreed:** the staff face's lookups, and Borrow and Return that the Copilot only prepares and the
staff member confirms, as D-07 requires; the two polish items from step 4. Five details were
settled while writing the exact contract, none of them a product change: the proposal reaches the
panel as one more card type through the existing event stream; the panel can re-read a proposal, so
a card restored after a reload shows its real state; Confirm answers with the whole proposal; the
Copilot names copies by their codes and never sees a copy's internal id; dates reach the model already
written as "3 Oct 2026", because the prompts must hold no digits (the number check's design).

**Built:** five staff lookups (members by name, a member's loans, a book's loans, overdue loans, a
copy by its code) and two preparing tools; the proposals table (migration 0005) and module:
preparing checks everything the change will check and stores a proposal bound to the user for 10
minutes; confirming locks the proposal's row and runs the circulation service as the user, via the
Copilot, so the loan, its activity event and the proposal's status commit together; a refused
change marks the proposal failed with the reason; confirm, cancel, failure and expiry each leave a
note in the conversation. The panel: a proposal card with its states (pending,
confirming, confirmed, failed, expired, cancelled) that refreshes every view a loan change affects;
member rows, a copy summary with its borrower, member names on staff loan rows; a single-book search
card folds into the detail that follows it.

**Verified:** the gate passed 23 of 23, with 557 backend and 184 frontend tests. They
include a race of two real database connections confirming the same proposal: exactly one succeeds,
and with the row lock removed the test failed 5 runs of 5. Then live, with the real model, signed in
as demo staff:

| Asked | What happened |
|---|---|
| "Who has Dune right now?" | looked up the book's loans: nobody has it, all 3 copies are available; 6.3 s |
| "Show everything overdue" | the 5 overdue loans, longest first, with borrowers and dates written "2 Sep 2026"; 5.5 s |
| "What is copy CP-0217?" | The Hobbit, on loan to Kenji Choi, due back 23 Sep 2026; 4.1 s |
| "Which books does Maya Hassan have?" | found the member and listed her 2 loans, one overdue; 8.7 s |
| "Borrow The Hobbit for Daniel" | several members are named Daniel: it listed them and asked which one; after "The first one" it prepared the proposal |
| "Borrow The Hobbit for Maya Hassan" | a proposal card for copy CP-0216, due 3 Oct 2026; nothing changed until Confirm |

In the browser, Confirm made the loan; the dashboard behind the panel refreshed at once (365 to 364
copies available), and the activity history showed "Borrowed The Hobbit (CP-0216) to Maya Hassan,
due 3 Oct 2026" by Demo Staff, marked Copilot. "Return Maya Hassan's Hobbit" found the actual loan
among her three and proposed its return; Confirm returned it. Cancel showed "Cancelled. Nothing
changed.", and the follow-up "Did that loan go through?" was answered "No, the loan did not go
through. It was cancelled, so no changes were made." After a page reload the confirmed card still
showed its outcome. With curl: a copy lent at the desk after the proposal made Confirm answer 409
"Copy CP-0216 is already on loan", mark the proposal failed and create no second loan; a second
Confirm answered 409 `proposal_resolved`; a proposal past its 10 minutes read as expired and refused
both Confirm and Cancel with 409 `proposal_expired`; a member got 403 from every proposal endpoint,
and the member Copilot declined to borrow and pointed to the desk. Every loan made during the walk
was returned, so the demo library ended as it began (119 on loan).

**What went wrong, and the fix**, each with a test shown to fail first:
- Once in four tries, the model answered "Borrow The Hobbit for Maya Hassan" with an empty reply
  after its lookups. The engine's retry for an empty reply forbade tools, so the model could not
  take its next step, and the turn ended in the plain fallback. An empty reply now gets one nudge
  with the tools still on offer.
- The activity list showed the confirmed action as "in 43 seconds": its clock ticks once a minute,
  and the list refreshed between two ticks. The clock is now never earlier than the moment the list
  was fetched.
- Titles the model writes in italics or bold italics showed their asterisks. The panel's formatter
  now renders both.
- The staff book card did not name who has a borrowed copy, although the data carried it. It now
  does; members still never see it.
- One model call in about 40 was refused by the provider with a 400 and did not recur in nine
  repeats. The panel showed "could not answer" with Try again, as designed. It is recorded in
  `../99-pending.md`, with two gaps left as demo debt: the new loan's id is stored on the proposal
  in a second commit, and old proposals are never deleted.

## Step 6 · The analyst: questions about how the library is used

**Agreed:** the analyst face in the staff panel, answering through typed metric queries rather
than generated SQL (D-08), with follow-ups and comparisons with earlier periods (A-X01 to A-X04).
The owner accepted the proposed metric catalogue and one new dependency, a charts library loaded
only when an answer has a chart (D-20). The contract fixed the rules that decide whether a figure is
right: which days each period preset covers, how a partial quarter is compared like for like, that a
total is computed over the whole selection rather than summed from rows, and that the server
computes every share and change.

**Built:** a metric service with the catalogue, period and comparison resolution, and fixed
parameterised queries per metric; the `describe_metrics` and `query_metrics`
tools on the staff face, with a table display chosen by the server. In the panel,
an accessible table with formatted cells and a total row, and a bar or line chart from recharts in a
separate file fetched only when needed.

**Verified:** the gate passed 23 of 23, with 661 backend and 206 frontend tests. The backend builder
broke nine behaviours one at a time (a total summed from rows, a partial quarter compared with a
whole one, empty months left out, unknown fields accepted, the member face given the analyst, among
others) and each made tests fail. Every metric query ran in under 6 ms warm and 20 ms cold on the
demo data, so no index was added. The main web app file grew by 3.7 kB; the chart code is a separate
369 kB file. Then live, with the real model, signed in as demo staff:

| Asked | What happened |
|---|---|
| "How many active loans are there?" | 119, the same as the dashboard; 5.1 s |
| "Which categories were borrowed most this quarter?" | a table and a bar chart for 1 Jul to 19 Sep 2026, marked "so far": Children 99 loans (15.4%), Fiction 87, of 641 in total; 6.4 s |
| "Only among members who joined this year?" | the same query with that one filter added: 211 loans, Children first at 19.4% |
| "How does that compare with last quarter?" | compared with 1 Apr to 19 Jun 2026: up from 152 to 211 (+38.8%), each category with its change |
| "Loans per month over the last 12 months" | Sep 2025 to Aug 2026 as a line chart, peak 277 in Aug 2026, 2,686 in total |
| "Which members will stop borrowing?" | said plainly that it cannot predict that, and offered what it can show |
| "Is technology's share of loans growing compared with the same period last year?" | yes over the last 12 months, 6.9% to 7.5% (123 to 201 loans); level so far this year at 7.4% |

The demo data's reader personas surfaced without being planted: Technology's share of loans rose
from 1.7% (late 2023) to 5.8% (2024), 7.2% (2025) and 7.4% (2026 so far), as software
professionals joined. In a browser, the bar chart, the two-series comparison chart with its legend,
the monthly line chart and the tables fitted the panel in the dark theme; a wide comparison table
scrolls sideways inside its card.

**What went wrong, and the fix**:
- OpenRouter refused a model call with a 400 for the second time that day, in the fifth call of a
  four-lookup turn. The same question then succeeded four times in a row, and a temporary patch that
  recorded the provider's reason caught nothing. The log carried only the status, so the cause could
  not be read afterwards. The log line now carries the provider's stated reason, cut short and with
  anything shaped like a key removed; tests shown to fail first prove the reason is logged and the
  key is not.
- The staff panel's header and hints still described only books, members and loans; they now
  mention the library's figures.
- Open, in `../99-pending.md`: "titles not borrowed" also counts books added after the period
  ended, and one Vitest worker crashed once under heavy machine load and did not recur.

**Also on 2026-09-19:** the owner set up Google sign-in (a Google OAuth client for the local app)
and signed in with Google; the account was created as staff because its address is in
`STAFF_EMAILS`. Google sign-in had until then been tested only against a fake identity provider.

## Step 7 · Forecasts, ISBN lookup and covers, catalog filters, polish

**Agreed:** honest forecasting (A-X05, D-09) with a method written in the project rather than a
statistics library; ISBN lookup and covers from Open Library (E17, D-13), after checking every
generated ISBN against it; catalog filters and sorting (E08); the polish list from the open items.
Three builders worked at once: the backend, the web app, and the demo catalog check.

**Built:** the forecast: the same month a year earlier times the trend, run from every past month
with two years before it to measure its misses, which set the likely range; refusals with what the
records have, what a forecast would need, and the trend instead. The ISBN lookup
endpoint with a timeout and a cache; filters, four sort orders and a categories endpoint; the
browser security policy extended to Open Library's cover hosts; a share lock that closes the race
between archiving a book and borrowing its copy; deletion of expired sessions and old proposals;
"titles not borrowed" ignoring books added later. In the web app: the forecast
chart with a shaded range, the filter bar bound to the address bar, covers with a placeholder,
"Look up" in the add-book form, "not found" for malformed links, and every page after sign-in in
its own file, which cut the first load from 718 kB to 526 kB. The catalog check,
`python -m app.seed.isbn_check`: all 267 ISBNs matched their books, none needed correcting, and 17
of the 19 titles without one gained one.

**Verified:** the gate passed 23 of 23, with 780 backend and 237 frontend tests. The
builders broke 13, 11 and 12 behaviours one at a time, and each made a test fail. The regenerated
demo library came out identical to the first one (286 titles, 484 copies, 5,482 loans, 120 on
loan, 6 overdue), now with 284 ISBNs. Live, with the real model, as demo staff: "Forecast borrowing
for the next three months" gave Sep 268, Oct 297 and Nov 243 loans, with likely ranges of 193 to
309, 229 to 364 and 196 to 305, from 35 months of history and a typical error of 13%; "Forecast
Fantasy loans for the next three months" was refused because Fantasy averaged 9.9 loans a month
against the 10 a forecast needs, and the trend was given instead (119 against 92 loans, +29.3%).
In a browser: covers matched their books; the catalog filtered to available Fantasy titles sorted
by date added from the address bar alone; "Look up" filled The Catcher in the Rye from its ISBN;
a malformed book link showed "Book not found"; the forecast chart drew the measured line solid,
the forecast dashed and the range shaded.

**What went wrong, and the fix**:
- The forecast ran high. Its own past tests showed the method had over-forecast most months (the
  median miss was 9% to 20% too high, depending on how far ahead), because the demo library grew
  fast and then slowed, and "last year times the growth" keeps assuming the fast growth. September's
  first 19 days pointed to about 235 loans against a forecast of 295, still inside the range but at
  its top. The forecast is now moved by the median past miss, so it sits inside its range where the
  method's own history says it belongs: 268 for September. The range and the refusal rules are
  unchanged. A test with a constructed series was shown to fail before the change.
- Open, in `../99-pending.md`: Open Library limits cover requests by ISBN to 100 per 5 minutes per
  address (requesting by cover id would avoid it); the lookup's year is the work's first
  publication year, which can differ from the edition's; two demo titles have no ISBN.

## Before publishing (2026-09-20)

The documentation was checked against the code, the README gained a table mapping the brief's
requirements to where each one lives, and the harness gained a README of its own. Two independent
passes then read the newest pages against the code and found 16 accuracy slips, from a wrongly
cited file for search to an overstated Origin check; all were fixed before publishing. The tracked
files were reviewed by hand and the gate run once more.

The repository's history is a single commit, so the build log no longer cites commit ids (D-22).
Before that history was replaced, the trees were compared: the same tree hash and the same 376
files before and after, so the one published commit carries exactly what the build produced. The
commit has been amended since, for the deployment and the documents that came with it, so it now
holds more files than it did that day.

CI gained a job for the harness checks, which were first run on Linux in a container to be sure
they pass there (20 of 20, the two Windows-only checks skipping themselves), and the pnpm version
was left to `package.json`, because naming it twice makes that action fail.

The image was also run in production mode against the demo database, to find deployment surprises
early: the health check passed, the interactive API documentation was hidden (404), the session
cookie came back Secure, HttpOnly and SameSite=lax, the response carried HSTS and the image policy
naming only the cover hosts, and `python -m app.seed --reset` refused to run, as it must. Google
sign-in was off in that run, because it had no client configured.

## Deployed (2026-09-20)

The repository was published at `https://github.com/Eslam93/mini-library-management-system` as a
single commit, and the application was deployed to the owner's AWS account:

- One EC2 instance (t3.micro, Amazon Linux 2023, 16 GB disk, 3 GB swap so the web build fits in 1 GB
  of memory) running the same Docker Compose stack as a laptop does: PostgreSQL, a one-shot
  migration, and the application.
- CloudFront in front of it, serving `https://library.eslamhamed.com` with a certificate issued by
  AWS and validated through DNS. The name is a record at the owner's registrar pointing at
  CloudFront, so nothing moved and their other sites were untouched. The session cookie is marked Secure, so a plain HTTP address could not have carried a
  sign-in. Caching is disabled and every header, cookie and query string is forwarded, so the
  Copilot's event stream arrives as it is sent.
- The instance takes traffic only from CloudFront's own address ranges, has no SSH key, and is
  managed through Systems Manager. The OpenRouter key is kept as an encrypted parameter and read by
  the instance at start, never written into the machine's start-up script.
- The instance's start-up script clones the published repository, builds the image, starts the
  stack and fills the demo library. Rebuilding the box is therefore one command.

**Verified live through the HTTPS address:** the health check; the sign-in page; demo sign-in
setting its cookie; the dashboard, catalog and book pages; and three Copilot turns, a staff lookup
in 6 seconds, a category breakdown, and a three-month forecast with its range.

The consent screen was then published, so any Google account can sign in. Publishing needs a home
page, a privacy policy and terms, so the app gained two pages it serves without a sign-in: what
this deployment stores about a person who signs in with Google, and the terms of using a
demonstration. Those pages also answer the question the demo buttons raise, which the README and
D-05 now answer too: there are no passwords anywhere in this system. A named user signs in with
Google; the demo buttons open a session on two shared accounts that hold no personal data, behind
a setting that is off in production by default.

Google sign-in was then added: its client id and secret, and the staff address
list, are encrypted parameters the instance reads, and the deployed address was registered as a
redirect URI with Google. Signing in with the owner's Google account created a staff user, because
that address is on the staff list. Any other Google account signs in as a member.

**What went wrong, and the fix:** CI had never run, and the first run failed twice over. A test of
the settings' defaults read the environment, which the workflow sets (`APP_ENV=test`), so it passed
on a laptop and failed in CI; it now clears those variables first. The pnpm action looked for
`package.json` at the repository root, where this project has none, so the frontend job stopped at
once; the workflow now points it at the application's own file. Both were found by running CI, not
by reading it.

## The last review, against the brief (2026-09-20)

The finished submission was read back against the assignment itself, by three reviewers working
apart: one matching every line of the brief to the code that satisfies it, one reading the
repository as a reviewer with twenty minutes, and one checking every documented claim against what
the code does.

The product answered every line of the brief, and each of the three minimum features was exercised
once more against the live deployment, not only in tests: a book was added, edited and deleted (a
book with no history is really deleted, and the address it had returns not found); search was run
by title, by author and by part of an ISBN; and a copy was borrowed and returned through the
Copilot's proposals, which the activity history recorded as made through the Copilot. The library
was left exactly as it was found, which the dashboard's counts confirmed.

The reviews found no defect in the product and nineteen in what was written about it. The ones that
mattered: the README made a reviewer read for seven minutes before reaching how to run it, so it
now leads with the live address and the table that maps the brief to the code; the claim that the
assistant "never invents a number" was stronger than the check, which compares runs of digits, so
it now says what the check does; the product specification described an ISBN that fills a form as
you type, where the form has a "Look up" button; the backend's own README still described the staff
assistant as it was at step 4, before lookups, proposals and the analyst; four pages still said
there was no remote and that CI had never run; and the demo library's size was quoted as a fixed
number, where the copies and loans depend on the day the seed runs.

Two gaps in the product were found worth recording rather than fixing, and are now in
`../99-pending.md`: archiving a book cannot be undone from the product, and a copy can be added but
never removed.

## Where it ended

The product is finished and delivered: the repository is published, CI passes on it, and the
deployment runs at the address above, with both roles and the Copilot working there. What is open
is recorded in `../99-pending.md`, and what was deliberately left out, with how it would be built,
is in `../50-designs/designed-not-built.md`.
