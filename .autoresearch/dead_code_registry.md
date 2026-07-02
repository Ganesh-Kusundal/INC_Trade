# Dead Code Registry

> Auto-maintained by the `code-reviewer` agent.  
> Add entries whenever speculative / YAGNI code is identified but not deleted.  
> Remove an entry once the file is either resurrected (with a real caller) or permanently deleted.

---

## Entries

| # | File Path | Lines | Last Git Touch | Reason Dead |
|---|-----------|------:|---------------|-------------|
| 1 | `brokers/dhan/async_http_client.py` | 450 | 2026-07-02 10:37:10 +0530 | **YAGNI** — speculative async HTTP client; `grep -r 'async_http_client' brokers/ --include='*.py' -l` returns only the file itself. Zero callers exist. Mirrors `DhanHttpClient` but was never wired into any workflow or test. |

---

## How to Resurrect a Dead File

1. Find the file's history:
   ```bash
   git log --all --oneline -- <file_path>
   git show <commit>:<file_path>
   ```
2. Remove the `⚠️ DEAD CODE` warning block from the module docstring.
3. Remove the `# ruff: noqa: F401` suppression comment.
4. Add at least one real caller **and** one integration/unit test.
5. Remove the entry from this registry.

---

## How to Permanently Delete Dead Code

1. Delete the file: `git rm <file_path>`
2. Remove the entry from this registry.
3. Commit with message: `chore: delete dead code <file_path> (YAGNI cleanup)`
