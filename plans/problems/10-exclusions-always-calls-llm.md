# 10 — `exclusions.py` always tries the LLM regardless of API key

**Severity:** Medium (gives confusing behaviour with no key).
**File:** `scripts/migrations/exclusions.py`.

```python
key = os.environ.get("CLAUDE_CODE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if key or True:
    s.log.info("Using Claude LLM for batched exclusions parsing...")
    ...
    resp = s.ask_llm(prompt)
```

The `or True` on line 97 forces the LLM path. With no API key set,
`s.ask_llm` falls back to `prompt_user(prompt)` which **pops a Tkinter
GUI** asking the human to paste the LLM's answer. That's almost
certainly not what's wanted from `./run migrate exclusions` on a
headless machine.

Compare `caterer_contacts.py` and `caterer_menus.py`, which both gate
the LLM call behind `if key:`.

### Fix

Remove `or True`. Restores the symmetric `if key:` pattern; the heuristic
fallback handles the no-key case (with the May-2026 caveat in #09).
