---
name: record
description: Write a finding, a measurement, a decision, a trap, or a negative result into the knowledge base with its evidence, its confidence, and what was not checked, or capture something noticed but not acted on. Use whenever something durable has been learned about how the project actually works, a real fork was decided, or something is spotted that will not be fixed now.
argument-hint: "[the finding, or nothing to record what was just established]"
allowed-tools: Bash(git *) Read Grep Glob Edit Write
---

# Record

$ARGUMENTS

The knowledge base is only worth reading because of what does not go into it. The discipline below
is the entire value, and it costs about four extra lines. Record in the same turn as the discovery,
while the evidence is freshest. **Do not ask permission to record.** Recording is the job.

The base lives at `docs/knowledge-base/`. The path-scoped rule `.claude/rules/knowledge-base.md`
holds the full rules and loads when you open a page there with `Read`.

## First: does it belong here at all

| It is | It goes to |
|---|---|
| how something actually works, a measurement, a decision and its reasoning, a trap, a negative result | the knowledge base |
| where we got to, status, next steps, anything stale in a week | `working/`, through `/handoff` |
| known, understood, and nobody is doing it | `99-pending.md`, one line, same turn, without asking |
| an environment trap that fails silently | `.claude/rules/working-here.md`, symptom, mechanism, fix, date; merge with an existing entry when the root cause is the same |

The test: would this still be worth reading a year from now? **Do not capture into `working/`.**
That is a slower way of losing it. The base never links into `working/`.

## Verify before you write

Immediately does not mean unverified. A wrong claim written here becomes the premise of every later
session. Check against the repository, the live system, or CI, not against recall. If you cannot
verify it, record it anyway, labelled honestly.

## What every claim carries

- **A confidence label:** verified · strongly inferred · tentative · unknown · historical.
- **The evidence itself:** the command and what it returned, the file and line at a commit, the run
  id. Not "we checked": what was checked and what it said.
- **What was not checked.** Deployed is not exercised, compiling is not working, reasoned is not
  demonstrated. Say which.
- **Its type**, so the reader knows what kind of sentence it is: fact, measurement, decision,
  opinion, trap, negative result. A measurement carries its date and commit and is written in the
  past tense. A changeable condition is never asserted in the present tense.

## Where it goes

- **A page** under the numbered folder that fits, with the header: `title` (what it settles),
  `status`, `as_of`, `last_verified`, `verification_method`, `scope`, `confidence` with why,
  `known_gaps`, `supersedes`, `reverify_when`. Add the three-line banner when the page carries
  volatile numbers. Add its row to `00-orientation/index.md`.
- **A decision:** an entry at the top of `decisions.md` with decision · options · why · by ·
  reversible · revisit when · supersedes.
- **A measurement's commit and command:** `_investigations/<date>-<name>/methodology.md`, linked
  from the page that cites it.
- **An external source:** a note in `_readings/`: what it says, what was taken, what was not, its
  own verification status.

## Correcting something already written

**You were wrong:** fix the claim, delete the wrong version, do not narrate the fix. Keep a visible
correction only when the old claim was load-bearing for somebody else, or when the correction is
about method rather than fact. **The world changed:** supersede, keep both, date both, link the
replacement, say why. Update the header too. Then **sweep by code symbol, not by phrase,** through
headings, table cells, worked examples, and the pages that cite the corrected one. A correction that
lives only where it was discovered has not been made.

## The three that do not bend

1. **Never record a secret value.** Record that it exists, where it is referenced, and how it is
   provisioned. The hook enforces this on Edit and Write only.
2. **Describe the system, not the people.**
3. **Keep negative results and contradictions.**

## Finish the job

Commit in the same turn, always with `-m`: a bare `git commit` opens an editor and hangs. Push when
there is a remote and the branch is not gated; when it is gated, push a branch and say a pull
request is needed. A finding sitting uncommitted does not exist for anyone else. Write the commit
message like the finding matters: `git log` on the base is a readable history of what was learned.
