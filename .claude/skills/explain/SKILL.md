---
name: explain
description: Explain one specific thing in full, pitched at a named audience, from what the code and the system actually do right now, or re-check a statement against the current tree and say whether it holds. Use when something needs to be understood rather than changed, when a previous answer needs the real version, or when a claim needs verifying.
argument-hint: "[what to explain] [for: me | a new engineer | a manager | a non-engineer]  or  verify: <statement>"
allowed-tools: Read Grep Glob Bash(git *) Bash(ls *) Bash(cat *)
---

# Explain

$ARGUMENTS

**If the argument is empty, explain the last substantial thing in this conversation.** That is the
common case: a long answer was given and the reader wants the real version. Do not ask what they
meant.

## Verify mode

`verify: <statement>` means: treat the statement as a claim, re-derive it from the current tree and
system, and answer with one of **Verified**, **Refuted**, or **Unknown**, followed by the evidence:
the file and line, the command and what it returned, the commit. Say what was not checked. A claim
that was true at an earlier commit and is not now is Refuted with the date it changed. This is the
same discipline the knowledge base uses, applied to a sentence.

## Audience

If no audience was given, assume the owner and say so; do not spend a turn asking. The audience
changes the answer more than the topic does.

| Audience | Pitch |
|---|---|
| **the owner** (default) | mechanism first. Names, files, line numbers. Assume the stack is known. Say what is surprising or wrong |
| **a new engineer** | orientation first: what it is for, how it hangs together, where to look. Name the traps early; they cost days |
| **a manager** | outcome and consequence. One sentence of mechanism at most, and only if it is the interesting part |
| **a non-engineer** | what it does for them and what it guarantees. No component names. An analogy must be load-bearing, not decorative |

When unsure of the level, go one notch more technical, not less.

## Read before writing

Do not explain from memory of this codebase. Trace the actual path from the real entry point:
`grep -rn "<entry>"`, then follow it; `git log --oneline -5 -- <files>` because recent churn changes
the answer. If the code and a document disagree, say so and give both. That contradiction is
usually a better finding than either source alone.

## Shape

1. One sentence: what it is and what it is for.
2. The path, in order: where a request enters, what it touches, where it leaves. Name the methods.
3. The one thing that surprises people. Every subsystem has one.
4. What you did not check, if the explanation has a soft edge.

Plain words, defined in the same breath. Name the real moving parts; an analogy supplements the
mechanism, never replaces it. Longer than the original is fine when the original was dense; that is
the difference from `/summarize`.

## Rules

- **Depth matches the audience, honesty does not.** Simplify the mechanism; never simplify away a
  limitation. If something is broken, badly designed, or unknown, say so in the same plain language.
- **Do not invent a rationale.** If it is unclear why something is the way it is, say so. A
  plausible reason recorded confidently is how a wrong belief becomes permanent.
- **Explaining is not changing.** Note anything worth fixing in `99-pending.md` and carry on.
- If the explanation turned out to be worth keeping, offer to `/record` it.
