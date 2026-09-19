---
name: pr
description: Open a well-formed pull request from the current branch, following the repository's template, branch model, and commit convention, with a plain-English body that carries the evidence and the test guide. Use when a change is ready for review on GitHub.
argument-hint: "[target branch] [--draft]"
disable-model-invocation: true
allowed-tools: Bash(git *) Bash(gh *) Read Grep Glob
---

# Pull request

$ARGUMENTS

A pull request is visible to everyone on the repository. **Say the destination sentence and get a
yes before creating it:** which branch, into which target, with which title.

## 1 · Preconditions

| Check | If it fails |
|---|---|
| not on the target branch | stop: switch to the working branch first |
| the task's own work is committed | say what is uncommitted. Files named in `working/<task>/pre-existing.txt` belong to the owner: leave them as they are, never commit or stash them. Commit the task's own paths before continuing |
| commits ahead of the target: `git log origin/<target>..HEAD --oneline` | stop: nothing to open |
| no pull request already open for this branch | stop and give its link |
| the target matches the project rule's branch model, or the branch sentence agreed in `/work` | ask one question with the options named |

## 2 · Discover the repository's own conventions

- **Template:** `.github/PULL_REQUEST_TEMPLATE/` (list, let them choose), then
  `.github/PULL_REQUEST_TEMPLATE.md`, `.github/pull_request_template.md`,
  `docs/pull_request_template.md`. When one exists, keep every section; write "N/A" rather than
  deleting one.
- **Title convention:** read it from the last twenty commit subjects, `git log -20 --format=%s`.
  Conventional commits when the log uses them; the dominant type when the branch mixes several.
- **Reviewers, labels, linked items:** whatever the project rule or CODEOWNERS says. Never assign a
  person the project rule does not name.

## 3 · The body

Write it so somebody who has not opened the code understands the consequence:

1. **What changed**, in behaviour terms, not files. "Users stayed logged out after a token refresh;
   now the refresh runs before the session check."
2. **Why it matters:** who was affected, what it unblocks, what stops happening.
3. **How to test:** the test guide from `/test-guide`, verbatim.
4. **Evidence:** the checks that ran and what they returned, with numbers. Not "tests pass".
5. **Not covered:** anything deliberately left out, anything the tests do not reach, any follow-up
   already known. A pull request that admits its own edges gets reviewed faster.
6. **Related items:** issues, with `Closes #n`.

Before writing, `git diff --name-only origin/<target>..HEAD`. If files changed that have nothing to
do with the stated purpose, say so in the body rather than quietly including them.

## 4 · Push and create

```bash
git push -u origin HEAD
```

If the push is rejected because the remote moved: `git fetch origin`, rebase onto the target, and
push with `--force-with-lease`. Never `--force`. If the rebase conflicts, stop and say so.

`gh pr create --base <target> --title "<title>" --body-file <file>`, with `--draft` when asked.
Write the body with the file tools first, so nothing is mangled by the shell.

## 5 · Verify and report

Read the pull request back from the server, not from the create command's output: number, URL,
source and target, additions and deletions, and the state of its checks. Report those, and say
which checks are pending or absent. More than twenty files changed is worth a sentence about
whether the change splits.
