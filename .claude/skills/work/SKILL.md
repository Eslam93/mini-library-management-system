---
name: work
description: Take a piece of work from a description or a GitHub issue through understand, one yes, an uninterrupted build, a local verify, and a hand-back with evidence. Use when picking up any task, bug, or feature that should be done end to end.
argument-hint: "[a description, or an issue number or URL]"
disable-model-invocation: true
---

# Work

$ARGUMENTS

Six beats: **intake, understand, agree, build, verify, hand back.** One yes, after Understand.
**This is a suggestion, not a process:** if the owner skips a beat, skip it and say nothing. Match
the beats to the size of the job. Nobody writes a plan to rename a variable.

**State the tier in one line the owner can override**, from the standing orders' table. The highest
signal wins: files touched, a new dependency or contract, design ambiguity, a hard-floor area. Tier 1
has no stop. Tier 2 stops once. Tier 3 stops once and adds a decision entry.

## 1 · Intake: get the item from wherever it lives

- **A description in their words** is enough. Do not send them away to write a ticket.
- **A GitHub issue or pull request:** `gh issue view <n> --json title,body,labels,comments`, or
  `gh pr view <n>`. If `gh` is missing or not signed in, say so and take the text instead.
- **A whole feature or epic:** say so and propose phases (2b). It does not fit one session.

## 2 · Understand: you do the reading, they do the deciding

**Do not write code during this beat.** Nearly every expensive mistake comes from acting on a
half-understood request, not from writing bad code.

| | |
|---|---|
| **The outcome** | what is true when this is done, in a form that can be checked |
| **The trigger** | what is broken or missing, and who it affects. For a bug: how to reproduce it |
| **The boundary** | what is explicitly not in scope |
| **The constraints** | anything non-obvious that must not break |

**You supply the code half.** Find and tell them which files and areas are involved, what the
current behaviour actually is, the pattern that already exists for this kind of change, the library
that already does it before you write a new one, and anything surprising. Then a bottom line of what
you understood, and **only the questions whose answer would change what gets built**, in one
message. If you can answer a question yourself, answer it and state it as an assumption they can
correct. Repeat until satisfied, and say so.

**2a · Who else is in this code.** When a remote exists: `git fetch origin --prune`,
`git log --oneline --since="3 weeks ago" --all -- <the paths you will touch>`, and the open pull
requests on the same repository. Say what you found before proposing anything.

**2b · Bigger than a session: phases.** Split by dependency, not by ticket. Name what each phase
makes possible and put the hardest unknown in its own phase. Each phase gets a brief a fresh session
can execute cold, in `working/<task>/phases/<n>.md`.

## 3 · Agree: one summary, one yes

A bottom line of what you are about to do, then the details, in the house writing style:

- where this sits and why it matters · the problem in their terms · what we have now, honestly
- **the outcome checklist:** one line per acceptance criterion in the shape *given <start>, when
  <trigger>, then <observable result>, verified by <how>*. Three to seven lines for a normal task;
  the full brief when the change touches security, persistent data, a migration, or another system
- the phases · what needs investigating first · decisions that will be needed later, flagged now
  rather than raised in the middle of the build · what is out of scope
- **the branch sentence:** which branch the work lands on, following the project rule
- the tier line

Then stop. **That is the only approval you ask for.** If they change something, fold it in and
restate only what changed. Write the agreed summary and checklist to `working/<task>/brief.md`:
after a compaction the `resume-brief` hook reads this session's brief back (the newest brief when
none is bound), so the build continues from
the agreement rather than from a summary. Commit a checkpoint before building. A real fork decided
here goes to `decisions.md` through `/record`.

## 4 · Build: uninterrupted

- **Git is the undo.** The checkpoint commit is the point to return to; the session's own
  checkpoints do not track changes made through the shell. Commit task work early, on task-owned
  paths only: `git add -- <paths>`, never `git add -A`, `git add .`, or `commit -a`. Files that were
  dirty before the task belong to the owner: leave them out of every commit.
- **Ask for a goal only when the finish condition is machine-decidable,** and only where the
  owner's client offers one (`/goal` in some of them). The owner types it, never the assistant:
  ask for the verify command and the checklist lines a check can prove. When it is not decidable, the brief file is the goal.
- **Follow the pattern that already exists.** If two disagree, say which you follow and why.
- **Write the tests as part of the work.** For a bug, the failing test that reproduces it first, and
  check that it fails before the fix. Name the tests that prove each checklist line. A build that
  compiles proves only that it compiles.
- **Stay inside the boundary.** No refactor, rename, reformat, or tidy the task did not ask for.
  Note it for the hand-back instead.
- **Pause only for the stop-list** in the standing orders. Everything else waits for the hand-back.
  **Two failed attempts at the same thing means the approach is wrong:** say so out loud and re-think.

## 5 · Verify

- `bash .claude/tools/verify.sh --full` must be green. Its output is the evidence.
- `/test-guide` walks the running app along the happy path and the covered bad scenarios, and
  records what was actually seen, including what was not exercised.

Independent code review is not part of this project's loop (see the project rule).

## 6 · Hand back, in this order

a. `git diff --name-only` before reading any content. Did this change something it should not have?
b. Read the test diff before the code diff, then the whole diff for things nobody asked for.
c. Report against the checklist, line by line: built, ran and did the thing, or not verified.
   Evidence, not claims: the command and what it returned.
d. The direction delta, one line: what shipped, in product terms, versus what was asked.
e. What to try themselves: open this, do this, expect that. The test guide carries it.
f. `/pr` when they say so. The test guide becomes the "How to test" section.
g. Anything learned goes through `/record`, with evidence and what was not checked. Open threads go
   to `99-pending.md`, never to `working/`. Then `/handoff` if the session is ending.

## What not to do

Ask for approval more than once · narrate every step while building · report partial success as
success · go quiet and try six things · treat the beats as a checklist to be seen completing.
