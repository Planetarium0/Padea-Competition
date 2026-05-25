# 24 — `host_webapp.py` uses `os.chdir`

**Severity:** Low.
**File:** `scripts/actions/host_webapp.py` (line 36).

```python
def main(port=DEFAULT_PORT):
    os.chdir(WEBAPP_DIR)
    ...
```

`SimpleHTTPRequestHandler` serves files relative to the process's
working directory, so changing into `webapp/` is the easiest way to
serve only that subtree. The downside is the process-wide side effect:

- If the script is ever imported (rather than executed as a script),
  the import changes the caller's cwd.
- Any future code added before the `serve_forever` loop that uses
  `pathlib.Path("…")` relative to the project root will break.

### Fix

Use a `partial(SimpleHTTPRequestHandler, directory=str(WEBAPP_DIR))`
or subclass with `directory=` set in `__init__`, instead of changing
the process directory. Available since Python 3.7.
