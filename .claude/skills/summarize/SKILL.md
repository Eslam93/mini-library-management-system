---
name: summarize
description: Give the short version of something, a long answer, a document, a diff, a session, a pipeline failure, without losing the caveats. Use when there is more material than anybody will read and the decision matters more than the detail, or when a response was too long.
argument-hint: "[nothing for the last answer, or a file path, a diff, a branch, or a topic]"
allowed-tools: Read Grep Glob Bash(git *)
---

# Summarize

$ARGUMENTS

**If the argument is empty, summarize the last substantial response.** The answer was long; they
want the point. Do not ask which part.

## The failure this skill exists to avoid

**A summary that lies by compression: the caveat dropped, the number kept.** "A database
connection takes 0.06 s" without "through `127.0.0.1`; through `localhost` it took 2.12 s" is not a
shorter version of the finding. It is a different, weaker claim that reads as stronger. **When
something has to go, drop the reasoning and keep the caveat.** Never the reverse.

## Before writing

Work from the material, not from recollection. For a session: `git log --oneline --since=<when>`,
`git diff --stat <base>..HEAD`, and the last `verify.sh` output. For a document or a diff: read it.

## Shape

**Lead with the single most important thing in one sentence.** If they read nothing else, that
sentence is the one that mattered. Then, only if there is more worth having: three to five bullets,
one idea each · anything that needs a decision from them, marked · anything not finished or not
certain · what was not checked. Stop there. A summary that runs to a page has failed at the one
thing it was for.

## Rules

- **Every number keeps its qualifier and its date.** If it will not fit with them, cut the number.
- **Distinguish done from written.** Code that was written but never executed is not done, and that
  distinction is the first casualty of compression.
- **Keep the corrections** when the wrongness is instructive: a check that was right about the wrong
  question teaches more than the finding that replaced it.
- **Do not smooth over a failure.** "Done after two failed attempts, both caused by <the cause>" is
  the honest version; "done" is not.
- **No new claims.** A summary derives from material already established. Something new noticed
  while summarizing goes to `99-pending.md`, not into the summary as though it had been verified.
- **No preamble.** Start with the point.

## When it is a diff or a pull request

Two short paragraphs, same voice: what changed, then why it matters, written so somebody who has not
opened the code understands the consequence. This is the version that goes into a pull request
description.

## When it is a failure

In this order: what broke · whether it is our change or not · what happens next. The middle one is
the question everybody actually has, and the one most summaries leave out.

## Afterwards

A summary is disposable: it goes in the reply, or in `working/` if it is session state. Anything in
it that is durable belongs in the knowledge base through `/record`, with its evidence.
