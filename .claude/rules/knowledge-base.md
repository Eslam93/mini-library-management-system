---
paths:
  - "docs/knowledge-base/**"
---

# Writing in the knowledge base

This holds facts: how systems work, measurements, decisions and their reasoning, traps, negative
results. Status and next steps go to `working/`. Known work nobody is doing goes to `99-pending.md`.
The base never links into `working/`; promotion runs one way, inward. The test for inclusion: would
this still be worth reading a year from now? This file is the full rule set.

## Every substantive claim carries

- **A confidence label:** verified · strongly inferred · tentative · unknown · historical.
- **Its evidence:** the command and what it returned, the file and line at a commit, the run id.
- **What was not checked.** Deployed is not exercised, compiling is not working, reasoned is not
  demonstrated.
- **For a capability, a status:** BUILT · RUNNING · SPECIFIED · PLANNED · EXPLORED · CLAIMED ·
  REPORTED. It inherits the weakest link; the gap between two statuses is itself the finding.

## Say what kind of sentence it is

| Type | Must carry | Tense |
|---|---|---|
| fact about structure or history | evidence pointer, label | present |
| measurement | date, commit or source, the command, label | past, dated |
| decision | the `decisions.md` fields | past, dated |
| opinion or recommendation | marked as such, the reasoning, what would change it | present, labelled |
| trap | symptom, mechanism, fix, date measured | present mechanism, dated observation |
| negative result | what was tried, what happened, date | past, dated |
| open question | who can answer it, what it blocks | `99-pending.md` |

## Volatile claims: write the measurement, never the state

Never assert a changeable condition in the present tense. "The backend is well tested" becomes
"As of 2026-09-19, on `main`, `uv run pytest` collected 523 backend tests." The test: could
someone make this sentence false next Tuesday by doing their job? If yes, date it and cite the
source. Dates are ISO days; add a time only when two measurements on one day differ.

## Pages

- A header on every substantial page: `title` (what it settles) · `status` · `as_of` ·
  `last_verified` · `verification_method` · `scope` · `confidence` (and why) · `known_gaps` (the
  most valuable line) · `supersedes` · `reverify_when`.
- On a page with volatile numbers, a three-line banner: measured when · expires when somebody does
  their job · stays true regardless.
- Numbered folders. Leave a section empty rather than speculative and say so in `index.md`, which
  has one row per page with a "what it settles" column. Create these when the first entry needs
  one: `what-we-do-not-know.md` groups gaps by root cause;
  `_investigations/<date>-<name>/methodology.md` holds the commits behind every number;
  `_readings/` holds notes on external sources; `50-incidents/` holds what went wrong, by date.
- `decisions.md`: one entry per real fork, newest first: decision · options · why · by ·
  reversible · revisit when · supersedes.

## What a check enforces, and what is on you

`verify.sh` runs `knowledge-check.sh` over this base. It refuses a durable page missing any of the
nine header fields or leaving one empty, a `status` outside its four values, a `confidence` not
opening High, Medium, or Low, an `as_of` or `last_verified` that is not a calendar day or is out of
order, a local link or `../` reference that does not resolve, a `repo:` path or `commit:` sha that
does not exist, a decision code `decisions.md` does not define, and, when `.claude/knowledge-drift.conf` lists them, a README count the tree
contradicts. `99-pending.md` and this base's `README.md` are exempt from the header only.

It cannot tell whether anything you write is true, whether the confidence word is right, or whether
a resolving commit supports the sentence beside it. Write evidence you want checked as
`repo:<path>` or `commit:<sha>`; anything else stays prose. A green result means structurally
valid, not correct.

## Corrections

- **You were wrong:** fix the claim, delete the wrong version, do not narrate the fix. Keep a
  visible correction only when the old claim was load-bearing for somebody else, or when the
  correction is about method rather than fact.
- **The world changed:** supersede. Keep both, date both, link the replacement, say why. Update the
  header too.
- **A correction that lives only where it was discovered has not been made.** Sweep by code symbol,
  not by phrase. Check headings, table cells, bullet leads, worked examples, and the pages that cite
  the corrected page. Fix the assertion; do not append a note beside it.

## The three that do not bend

1. **Never record a secret value.** Record that it exists, where it is referenced, and how it is
   provisioned. A hook enforces this on Edit and Write only.
2. **Describe the system, not the people.** Knowledge concentration is a property of the code.
3. **Keep negative results and contradictions.**

## `99-pending.md`

One line, same turn, without asking. Grouped by who can act: only the project team · needs a
decision · we can do this ourselves · worth doing when someone is in that code anyway. Priority
`P0` `P1` `P2` `?`. Link each item to the page with its evidence. Demo-posture shortcuts carry the
tag `demo-debt`.

## Mechanics

Commit in the same turn. Kebab-case file names that say what the page settles. One authoritative
page per claim; link, do not copy. 150 to 400 lines per page. LF endings; never round-trip a page
through PowerShell file cmdlets. No em dashes.
