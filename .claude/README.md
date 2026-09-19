# The working harness

This folder is how the project was built, not part of the application. It holds the rules the AI
assistant reads every session, the skills it can be asked to run, four hooks that enforce what
matters, and the checks that decide whether a step is done. It ships with the code on purpose
(D-16), so a reader can see the method as well as the result. The story is in
`../docs/knowledge-base/40-method/how-this-was-built.md`.

| Path | What it is |
|---|---|
| `rules/` | loaded every session: how we work here, the project's own facts, the writing rules, and the traps that fail silently, plus one rule that loads only when a knowledge-base page is opened |
| `skills/` | named procedures the owner can ask for, such as taking a piece of work end to end, or recording a decision |
| `hooks/` | the four enforced guards, each with a PowerShell and a Bash version |
| `tools/` | the checks: `verify.sh`, the project's own `verify.project.sh`, the knowledge-base validator, and the self-tests of both |
| `settings.json` | wires the hooks into the assistant |

## The checks

```bash
bash .claude/tools/verify.sh          # the harness checks and the knowledge base
bash .claude/tools/verify.sh --full   # the above, plus lint, types, tests and build for both halves
bash .claude/tools/verify.sh --canary # must fail: a check that cannot go red proves nothing
```

`REQUIRE_DB=1` makes a missing PostgreSQL fail the tests instead of skipping them.

## The four hooks

- **guard-secrets** blocks writing a secret value into any file through the editing tools.
- **guard-commands** blocks the destructive commands on its list, which is empty today and grows from incidents.
- **verify-on-finish** blocks ending a turn in which a test was weakened, skipped or deleted.
- **resume-brief** restores the agreed brief after the conversation is compacted.

None of them sees a browser, a network call or anything outside this repository. They are guards on
the assistant's own edits and shells, and nothing more.

## Running the hooks on macOS or Linux

`settings.json` wires the PowerShell versions, because this project was built on Windows. The Bash
versions sit beside them and take the same input: replace each command in `settings.json` with
`bash "${CLAUDE_PROJECT_DIR}/.claude/hooks/<name>.sh"` to use them. The self-tests
(`bash .claude/tools/hooks.test.sh`) exercise the Bash versions everywhere, and the PowerShell
versions where PowerShell is on PATH.
