---
title: What the library system is, what it does, and what it deliberately does not do
status: verified
as_of: 2026-09-20
last_verified: 2026-09-20
verification_method: Written from the assignment brief and the owner's product definition, then agreed with the owner on 2026-09-19. It specifies; what is built is recorded in the README status and the build log (as of 2026-09-20, steps 0 to 7 and the deployment: C01 to C08, E01 to E18, and the Copilot with its member, staff and analyst faces, including confirmed Borrow and Return and A-X01 to A-X05; A-X06, the stretch, is designed but not built, by the owner's choice)
scope: The product boundary, the features with their acceptance lines, the AI Copilot, and the delivery order. Implementation detail lives in the decisions and the code
confidence: High for scope and rules, because the owner locked them. High for the AI acceptance lines too: A-X01 to A-X05 were exercised against the real model and the generated library on 2026-09-19 and 2026-09-20
known_gaps: No screen-by-screen UX yet. The analyst's metric catalogue is specified in decisions.md (D-20), not here
reverify_when: A feature ships, a scope decision changes in decisions.md, or the assignment brief is clarified
---

# Product specification

## The product in one paragraph

A catalog and circulation system for a single library, used by staff and members. It manages book
titles and their physical copies, members, borrowing and returns, due dates, availability, history,
and basic operational visibility. Staff and members sign in with different permissions. One AI
Copilot works on top of the product's existing capabilities: members use it for discovery, staff
use it to look things up and to borrow or return with confirmation, and staff can ask plain-language
questions about library operations and get answers computed from the data.

**The scope rule:** the AI exposes and operates capabilities that already exist in the product. It
does not introduce new business workflows. No reservations because the AI could make them, no
procurement because a manager might ask, no messaging because an assistant could send reminders.

**The story it tells:** first the assignment itself; then the minimum domain concepts that make it a
credible circulation product (copies, members, loans, history, roles); then one permission-aware AI
layer over those real capabilities, instead of a generic chatbot.

## 0 · Foundation decisions

| Decision | Choice |
|---|---|
| Library structure | a single library |
| Catalog model | a Book (the title) is separate from its Copies (physical items) |
| Borrowing model | a Loan connects a Member and a Copy |
| Availability | derived from active loans, never stored |
| Concurrency | at most one active loan per copy, enforced by the database |
| Roles | Staff and Member only |
| Loan period | a default due date, adjustable per loan |
| History | loan history is preserved |
| Removing records | delete when nothing depends on the record; archive when history exists |
| Search | title, author, ISBN, plus simple filters |
| AI | one Copilot module with three faces, each with its own tools and permissions |
| AI writes | only after the user confirms the exact proposed action |
| Analyst | read-only; answers are computed from the data, never generated |
| Demo data | generated from reader personas: three years of history |
| Out of scope | branches, fines and payments, reservations, notifications (full list in section 6) |

## 1 · Core: the assignment

Build these first. When they work, the assignment is satisfied.

| ID | Story | Done means |
|---|---|---|
| C01 | **View catalog.** As staff, I see the library's books | a catalog page with title, author and availability |
| C02 | **Add book.** As staff, I add a book to the catalog | title and author required; ISBN, category, year, description optional; the first copy is created with it |
| C03 | **Edit book.** As staff, I correct or update a book | the form is prefilled, validation shows inline, success is confirmed |
| C04 | **Delete book.** As staff, I remove a book created by mistake | confirmation required; a book with loan history is archived instead of deleted |
| C05 | **Borrow.** As staff, I lend an available copy to a member | an active loan with a due date exists and the copy becomes unavailable. Two simultaneous attempts on one copy cannot both succeed (database constraint) |
| C06 | **Return.** As staff, I return a borrowed copy | the loan gets its return date and the copy becomes available |
| C07 | **Search.** As a user, I search by title, author or ISBN | fast keyword search with a useful no-results state |
| C08 | **Availability.** As a user, I see at once whether a book can be borrowed | "Available", "All copies borrowed" or equivalent, clearly visible |

**Terminology.** The brief says "checked in (borrowed)" and "checked out (returned)", which is the
reverse of standard library usage. The product uses **Borrow** (check out) and **Return** (check
in), and the README maps the brief's wording to these so the core requirement is visibly covered.

Borrow flow: search book → book details → choose an available copy (the first available copy is
preselected) → choose member → confirm → loan created.
Return flow: find the borrowed copy → return → confirm → loan closed → copy available.

## 2 · Core enhancements: the product we ship

These make the assignment believable as a real product. All are part of the submission.

| ID | Story | Why it earns its scope |
|---|---|---|
| E01 | **Multiple copies.** Staff add several copies of one title | real domain maturity for modest complexity |
| E02 | **Members.** Staff create, view and search borrowers | otherwise borrowing is only a status toggle |
| E03 | **Due dates.** Every loan has a due date | turns borrowing into a circulation workflow |
| E04 | **Overdue.** Staff see which loans are past due | high operational value, simple concept |
| E05 | **Loan history.** Staff see past borrowing and returns | preserves history, shows correct state modelling |
| E06 | **Book detail.** Metadata, copies, availability and loans on one page | a coherent product, not disconnected CRUD pages |
| E07 | **Member detail.** Current and previous loans | the page staff need during circulation work |
| E08 | **Filters and sorting.** Availability, category, sensible sort orders | search that is usable without scope growth |
| E09 | **Circulation workspace.** A dedicated Borrow and Return screen | the most frequent staff task, optimised |
| E10 | **Dashboard.** Available, borrowed and overdue counts, recent activity | operational visibility, not decorative charts |
| E11 | **Activity history.** Borrow, return, add, edit, archive are recorded | a strong production signal; AI actions appear here too |
| E12 | **Authentication.** Sign-in before protected functionality | Google sign-in, plus clearly labelled demo sign-in for each role so a reviewer can test both |
| E13 | **Role-based access.** Staff and Member experiences differ | enforced on the server, not only hidden in the UI |
| E14 | **Member self-service.** Members search and see their own loans and history | the second persona gets real value |
| E15 | **Archive protection.** Records with history are archived, not destroyed | data integrity |
| E16 | **Finished UX states.** Empty, loading, error, validation, success, confirmation | the cheapest way to make the product feel finished |
| E17 | **ISBN lookup and covers.** In the add-book form, "Look up" fills title, author and year from the ISBN; covers show in the catalog and on a book's page | added 2026-09-19: cheap and visibly more usable (D-13) |
| E18 | **Public notices.** A privacy notice and terms, readable without signing in | added 2026-09-20: a sign-in provider asks for them before it lets any account in (D-24) |

Staff navigation: **Dashboard, Catalog, Circulation, Members, Activity.**
Member navigation: **Catalog, My loans, History.**
No more top-level sections than that.

**Sign-in details.** People who sign in with Google become Members, unless their address is on the
staff list. The demo sign-in (one button per role) is controlled by configuration and says clearly
that it is a demo. Out of scope: account recovery, invitations, organisations, teams, custom
permissions, and any role matrix beyond the two roles. Cut line: if Google sign-in consumes
disproportionate time, keep authentication and roles, and drop SSO.

## 3 · The Copilot: one module, three faces

A face is a system prompt, a set of tools, and a permission scope. Everything else is shared: the
model access, the tool-calling loop, streaming, the confirmation step, the activity record, and the
checks on what the model may say.

| Face | Who | What it does |
|---|---|---|
| Member | Member role | catalog discovery, availability, the member's own loans |
| Staff | Staff role | operational lookups; Borrow and Return with confirmation |
| Analyst | Staff role, in the same panel | questions about library operations, answered from the data |

Staff see the staff and analyst faces as one panel, so the code carries two faces and the analyst's
tools belong to the staff face (D-06). The role decides what data the Copilot can reach, which
tools it has, and what it may propose or execute. Results appear with the product's normal
components (book cards, loan tables), not only as text.

### 3.1 Member face

| ID | Story | Tools |
|---|---|---|
| A-M01 | **Natural-language discovery.** "Show me available science fiction", "anything by Frank Herbert?" | search catalog, get book, get availability |
| A-M02 | **Explain availability.** "Can I borrow Dune?" → "Two copies exist; one is available now." | get availability |
| A-M03 | **My loans.** "What do I have?", "When is The Hobbit due?", "Anything overdue?" | my loans, my history (no member id parameter: it is always the signed-in member) |
| A-M04 | **Guide by doing.** "How do I find books about machine learning?" runs the search and shows results instead of describing clicks | search catalog |

The member face does not pretend to reserve, renew, contact staff or take payments: those features
do not exist.

### 3.2 Staff face

| ID | Story | Tools |
|---|---|---|
| A-S01 | **Operational lookup.** "Who has Dune?", "Which books does Maya have?", "Show everything overdue." | search catalog, search members, book loans, member loans, overdue loans |
| A-S02 | **Prepare a borrow.** "Borrow The Hobbit for Maya." → resolves member, book and an available copy, shows the due date, asks to confirm | the same lookups, then borrow after confirmation |
| A-S03 | **Prepare a return.** "Return Maya's Hobbit." → resolves the active loan, asks to confirm | the same lookups, then return after confirmation |
| A-S04 | **Investigate.** "Why does Dune show unavailable?", "Show this member's history." | the lookups above |

Write actions available to the AI: **Borrow and Return only.** No deletion, bulk operations, member
changes, or permission changes. The pattern for every write: intent → resolve entities → show the
proposed action → user confirms → execute → show the result. The AI never mutates silently.

### 3.3 Analyst face: ask your library

The product is "ask questions about library operations in plain language", not "AI that queries the
database".

| ID | Story | Done means |
|---|---|---|
| A-X01 | **KPI questions.** "How many active loans are there?" | the figure, from the data, optionally with a breakdown |
| A-X02 | **Exploration.** "Which categories were borrowed most this quarter?" | a table (and a chart where it helps) plus a short reading |
| A-X03 | **Follow-ups.** "Only among members who joined this year?" | the previous question re-run with the new filter |
| A-X04 | **Explanations.** "37%" becomes "Technology was 37% of loans this period, against 29% in the previous equivalent period" | comparisons against a previous period are built in |
| A-X05 | **Honest forecasting.** "Forecast borrowing for the next three months" | a forecast with a range when there is enough history (24 months to forecast from, plus enough later months to test the method on: 32 for a three-month forecast); otherwise it says what it has, what it would need, and offers the trend instead |
| A-X06 | **Exploratory questions** (stretch). Questions the metric catalogue cannot answer | the model drafts a read-only query that a server-side gate checks before running; the answer is labelled exploratory |

How it answers (D-08): the model chooses from a catalogue of metrics, groupings, filters, periods
and comparisons, and the server runs fixed, parameterised queries. Follow-ups become changes to
those choices. Every number in an answer must come from the query results.

### 3.4 Rules for all three faces

| Requirement | Behaviour |
|---|---|
| Permissions | the Copilot has exactly the signed-in user's permissions |
| Source of truth | it never invents facts about the data; numbers come only from tool results |
| Member privacy | members reach only their own account data |
| Management data | analyst answers are read-only |
| Mutations | executed only after the user confirms the exact proposed action |
| Audit | AI-triggered actions appear in normal activity history, marked as via the Copilot |
| Failure | the product works fully without the Copilot; it falls back to normal search and workflows |
| Ambiguity | it asks before acting when a name, book or copy is ambiguous |
| Transparency | it shows which entity and which action it resolved |
| Destructive operations | not available to the Copilot |
| SQL | users never see or provide SQL |

## 4 · Delivery order

Ordered by value (D-14). Each step ends runnable, tested and documented, so work can stop after any
of them.

| Step | Delivers |
|---|---|
| 0 | repository, harness, knowledge base, the application skeleton running locally |
| 1 | the core (C01 to C08) on the full data model, with activity recorded from the start |
| 2 | sign-in (demo and Google), Staff and Member permissions, member self-service |
| 3 | generated seed data, dashboard, overdue, book and member detail, circulation workspace |
| 4 | the Copilot module and the member face |
| 5 | the staff face, with confirmed Borrow and Return |
| 6 | the analyst face: metrics, follow-ups, explanations, tables and charts |
| 7 | forecasting, ISBN lookup and covers, filters and sorting, activity page, archive rules polish |
| 8 | stretch: exploratory questions (A-X06) |
| end | documentation pass, publishing the repository, deployment, the demo video script |

This splits the brief's second milestone: its high-value half comes before the AI and its polish
half after, so an early stop still leaves a working Copilot.

## 5 · Later, not now

Legitimate extensions that are not part of this submission.

| ID | Feature | Why later |
|---|---|---|
| L01 | Reservations and holds | queues, expiry and notification semantics |
| L02 | Renewals | lending-policy logic |
| L03 | Email or SMS reminders | external communication infrastructure |
| L04 | Fines | payments and policy complexity |
| L05 | Lost or damaged workflows | operational depth this demonstration does not need |
| L06 | Several branches | a large domain expansion |
| L07 | Bulk imports | useful in production, weak in a demo |
| L08 | Custom reports | the analyst face covers exploration |
| L09 | Recommendations | not enough behavioural data |
| L10 | AI metadata enrichment | deterministic book APIs do it better (E17) |
| L12 | AI bulk actions | too risky for this exercise |
| L13 | Shelf and location management | outside the demonstration goal |
| L14 | Configurable lending policies | turns a simple product into an admin platform |
| L15 | More staff roles | complexity without matching value |

L11 (AI forecasting) moved into scope as A-X05 on 2026-09-19, because the generated history is long
enough to forecast honestly (D-09).

## 6 · Explicitly out of scope

Multiple branches · fines or payments · reservations · renewals · messaging or reminders ·
procurement · inter-library loans · complex lending policies · configurable roles · reviews or
social features · gamification · AI recommendations · a general-purpose chatbot · destructive AI
actions · user-written SQL · forecasting without enough history.

If one of these comes up during the build, the default answer is **no**.
