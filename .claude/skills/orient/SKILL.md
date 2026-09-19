---
name: orient
description: Report where this project stands at the start of a session, before anything is done. What happened before now, what the tree is doing, what is deployed when that can be checked, whether it still verifies, and the one thing most worth doing next. Use when picking the project up after any gap, or when unsure what the last session left behind.
disable-model-invocation: true
allowed-tools: Bash Read Grep Glob
---

# Orient

A fresh context knows nothing, and the expensive failure is not knowing that. Six steps, then
**one short report and stop.** Do not narrate the steps as you go.

**Orienting and deciding are different jobs, and the second one is not yours.**

## 1 · Where am I, and what applies here

```bash
bash .claude/tools/layout.sh --report
```

If it reports a root other than this repository, stop and say so. Read
`.claude/rules/standing-orders.md` and the project rule beside it, and carry them into the session.
The branch model and where the work actually is are the facts that prevent the expensive mistake.

## 2 · What happened before now

```bash
cat working/status.md 2>/dev/null
ls -t working/handoffs/ 2>/dev/null | head -3
git log --oneline -10
```

The git log is the check on the status file. **If the newest commit is well after the status
file's date, trust the log and say the status file is stale.** Then skim `99-pending.md` in the
knowledge base for `P0` items.

## 3 · What the tree is doing

```bash
git fetch origin --prune                          # only when a remote exists
git status -sb
git log --oneline @{upstream}..HEAD 2>/dev/null   # unpushed
```

**Fetch before relying on any of it.** A branch read from a stale ref shows the world as it was
when the ref was last fetched. Uncommitted work means somebody was mid-task. Say what is
uncommitted and leave it.

## 4 · What is actually deployed, when the project rule names a way to check

Git does not know what is on the server. When the project rule names a deployed-state check (a
health endpoint that reports the running commit, a deploy tag, a file on the host), run it and
compare: `git log --oneline <deployed-commit>..origin/<trunk>` is what is not yet live. When there
is no such check, say so rather than guessing.

## 5 · Does it still verify

```bash
bash .claude/tools/verify.sh
```

**This is the step people skip and it is the one that saves the hour.** Without it a session spends
its first stretch trying to get the basic thing working again, having assumed it already did. If it
fails, that is the session's first job, not something to work around. Add `--full` when the
project's own checks are wired in `verify.project.sh`.

## 6 · Report

Five lines, no headings:

1. which branch, and whether it is ahead of its upstream
2. where the last session got to, with its date
3. what is uncommitted or unfinished
4. what verify reported
5. **the one thing most worth doing next**, named. Not a list of five.

Then stop and let the human choose.

## What this must not do

- Read the whole knowledge base. It is for searching, not preloading.
- Re-derive findings that are already written down.
- Fix anything it finds. Note it in `99-pending.md` and carry on.
- Skip step 5 because the last session said it built.
