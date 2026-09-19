# Things that fail silently

Every entry here returns something that looks normal and is wrong, which is why each one earns a
line in every session's context. The general entries come first, most of them about Windows with
Git Bash and PowerShell 5.1. The project's own traps follow, each with the date it was measured.
Every entry gives the symptom, the mechanism, and the fix. Before adding one, search for the same
root cause. Same cause with a different symptom means merge, not a new entry.

## Shell and tooling

- **`${BASH_SOURCE[0]}` is whatever the caller typed**, so a `cd` early in a script breaks every
  path derived from it, including the script's own, and a missing dependency then fails silently.
  Resolve `_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` before any `cd`, and `exit 1` on
  a missing dependency, never `&&`.
- **An argument starting with `-` is parsed as an option**, by `grep`, `yes`, `printf`, and most
  tools. `grep` and `grep -v` both return empty, so a static check goes green with none of the work
  done; `yes "- text"` fails silently inside a pipeline. Use `grep -E -e "$pattern"`, `printf --`,
  and `--` before any such argument.
- **An empty set passes every "is it small enough" check.** An unmatched glob runs the loop once
  with a name that does not exist. Count the files as well as the lines, and fail on zero.
- **A pipeline or a `;` sequence reports the exit code of its last command only.**
  `pytest | tee log` exits 0 when the tests failed. Use `set -o pipefail`, or check each command
  separately.
- **A quote character inside `${var:-default}` is syntax, and `bash -n` cannot see it.** An
  apostrophe in the default opens a string that runs on to the next apostrophe in the file. Assign
  the default on its own line in single quotes.
- **`git ls-files` lists only tracked files**, so a sweep built on it is blind to new ones, which is
  exactly when it matters. Use `git ls-files --cached --others --exclude-standard`.
- **`cmd /c` in Git Bash runs nothing and exits 0**, and `gh api /repos/...` with a leading slash
  is rewritten into a filesystem path. MSYS converts a leading `/x` for native programs. Write
  `cmd //c` and `gh api repos/...` without the slash. **Do not cure this with
  `MSYS_NO_PATHCONV=1` in the environment:** it also stops every POSIX path from being converted,
  so `git -C /c/work/repo` and `node /c/work/x` fail with "no such file" while `C:/work/repo` works.
- **`node -e` from Bash mangles backslashes and reports the error on the wrong line**, and `node`
  reads an MSYS path like `/c/work/x` as `\c\work\x` on the current drive. Put any one-liner with a
  backslash or a regex in a `.js` file, and pass Windows paths to native programs.

## PowerShell 5.1

- **Redirecting a native command's stderr under `$ErrorActionPreference = 'Stop'` makes it
  terminating.** One ordinary git warning kills the script, and `2>$null` does it exactly as much as
  `2>&1`. Suspend the preference for the call in a try/finally, or do not redirect.
- **A here-string does not reach a native command's stdin.** `git commit -F - @'...'@` passes the
  text as arguments, and the next command's success hides it. Use the Bash tool's heredoc for stdin,
  and verify the result, not the API's message.
- **Piping a string to a native command prepends a UTF-8 BOM**, so the far side fails on the first
  token only. Write the text to a file with a BOM-less encoding first, and pass the file.
- **No `&&`, `||`, `??`, or ternary.** Parse errors, not warnings.
- **In PowerShell, `bash` can be WSL rather than Git Bash.** Where WSL is installed,
  `System32\bash.exe` comes before Git on PATH; it runs Linux and reads `C:\x` as `C:x`. Commands
  started from Git Bash never see it, because Git leads PATH there. Run the harness scripts from
  Git Bash, or call Git's own `bash.exe` and accept it only if `uname -s` says MINGW, MSYS, or
  CYGWIN.
- **A `.ps1` without a UTF-8 BOM is read in the ANSI codepage by PowerShell 5.1**, so every
  non-ASCII character in the source becomes two wrong ones, and anything the script writes carries
  them. Give any `.ps1` holding non-ASCII a BOM; `verify.sh` checks it.

## Git and branches

- **A branch that is behind shows the tree as it was when the branch was cut.** Check any claim
  about a file against the branch it will merge into: `git show <target>:<path>`.
- **Before merging a branch, check what it deletes:** `git merge-tree --write-tree`, then
  `--diff-filter=D`. The diff people read is the one they asked for.
- **`git diff --stat` draws an all-minus bar for any heavily negative change.** Use `--name-status`
  to ask about deletions.
- **`git -C <subfolder>` acts on the enclosing repository when the subfolder is not a repository of
  its own**, so a question about the subfolder's remote or branch is answered about the parent.
  Test for `<subfolder>/.git` before asking git anything about it.

## Hooks

- **A hook matched on `Bash` alone misses commands that run through PowerShell.** Match both. Hook
  `timeout` is in seconds. The first character of stdout decides how output is parsed, so keep it
  quiet. Normalise path separators before matching file paths. Hooks do not hot-reload: restart the
  session after changing one.
- **A path-scoped rule does not load for a shell read or a shell edit.** `cat`, `grep`, or `awk` on
  a file under `docs/knowledge-base/` leaves `knowledge-base.md` out of context; the `Read` tool on
  the same file brings it in. A session that prefers the shell writes knowledge-base pages without
  the rule that says how. Open one page with `Read` first.

## Local database

- **`localhost` costs two seconds per database connection on Windows.** Symptom: the health check
  timed out and returned 503 against a healthy Postgres, while a test with no timeout passed.
  Mechanism: `localhost` resolves to `::1` first, Docker publishes the port on IPv4 only, and
  Windows takes about two seconds to refuse the IPv6 attempt before falling back. Measured: 2.12 s
  through `localhost`, 0.06 s through `127.0.0.1`. Fix: use `127.0.0.1` in `DATABASE_URL`.
  2026-09-19.
- **The default Postgres ports may already be taken on a development machine.** The compose file
  publishes Postgres on `127.0.0.1:55432`, not 5432; set `DB_PORT` to change it. 2026-09-19.
