---
name: handoff
description: Write the state of this session to a file so the work survives a compaction, a stop, or a change of hands. What was done, what is left, what was tried and failed, what will surprise the next person. Use at the end of a session, before a long break, when the context is getting long, or when passing work to somebody else.
argument-hint: "[short slug for the file name, or who this is for]"
disable-model-invocation: true
allowed-tools: Bash(git *) Read Write Glob Grep
---

# Handoff

$ARGUMENTS

**Write it to a file, not into the conversation.** A long session gets compressed and things get
dropped; a file does not. This is also how you pick the work up on Monday having forgotten all of
it.

## Where

`working/handoffs/<yyyy-mm-dd>-<slug>.md`, and then refresh `working/status.md` so `/orient` finds
the newest state in ten seconds. **Not the knowledge base.** This is status, and status ages badly.
A durable fact learned along the way goes through `/record`; an open item goes to `99-pending.md`.
Link to those from here rather than repeating them.

Leave `working/<task>/brief.md` where it is while the task is in flight: the `resume-brief` hook
reads it back after a compaction.

## What goes in it

- **One paragraph** anybody can read in ten seconds and know whether to read the rest.
- **What was done**, with commit hashes or the pull request, so it can be found without this file.
- **What is left**, in pick-up order.
- **Anything waiting on a person**, and who.
- **What was tried and did not work.** The section that saves the most time and the one most often
  left out. A dead end nobody recorded gets walked down twice.
- **Anything that will surprise the next person:** a trap discovered, a command that needs a flag, a
  check that lies. If it is durable, it is already in `working-here.md` or the base; link it.
- **The state of the tree:** branch, uncommitted files, unpushed commits, and whether `verify.sh`
  passes.

## Rules

- **Reference, do not copy.** A pasted diff is stale the moment somebody pushes. Cite the commit or
  the file and line.
- **Never a secret value.** Say where it lives and how to get it.
- **Be honest about what is unfinished.** Partial success is not success.
- **Say what is not verified.** If something was written but never run, that is the single most
  important line in the file.

## Gather it

```bash
git log --oneline -10
git status -sb
git log --oneline @{upstream}..HEAD 2>/dev/null
bash .claude/tools/verify.sh
```

Then tell them the path, give the one-paragraph version in the conversation, and if the tree has
uncommitted work, say so plainly and ask whether to commit it.
