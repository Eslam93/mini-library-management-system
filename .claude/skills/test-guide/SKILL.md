---
name: test-guide
description: Write the plain-English steps to try a change by hand, the happy path and the bad scenarios it covers, then run the stack and walk them. Use after a build, before a hand-back or a pull request, or when someone asks how to test a change.
argument-hint: "[nothing for the change in flight, or a branch, pull request, or feature name]"
disable-model-invocation: true
---

# Test guide

$ARGUMENTS

Two readers: the owner trying the change now, and whoever reviews the pull request later. One
document serves both. It lives at `working/<task>/test-guide.md` while the work is in flight, and
the same text becomes the "How to test" section of the pull request.

## Shape

1. **Preconditions.** What must be running or seeded, in one or two lines, with the start command
   from the project rule.
2. **The happy path.** Numbered steps: open this, do this, expect that. Every step names an
   observable result. "It works" is not a result; "the copy's row shows the status Borrowed" is.
3. **The bad scenarios this change covers.** One block each: the setup, the action, the expected
   refusal or fallback, and the checklist line it proves. Only the scenarios the change actually
   handles. Say plainly which failure cases are not covered.
4. **What was not exercised**, and why.

## Run it

Start the stack with `/run` where it exists, otherwise with the command in the project rule. Walk
every step yourself and record beside it what you saw: the screen, the response, the log line.
A step you could not perform stays in the guide, marked "not exercised". Never write "verified"
beside a step nobody ran, and never let a compiled build stand in for a running one.

## Rules

- Plain words, per `writing.md`. The reader may be a tester, a manager, or a reviewer.
- Internal names only where the reader has to type them.
- Numbers keep their qualifiers: "the Copilot answered in 6.3 s, once, with the real model".
- If a step reveals a defect, do not fix it inside the guide. Report it in the hand-back, and note it
  in `99-pending.md` if it will not be fixed now.
