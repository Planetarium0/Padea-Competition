# 04 — `./run script verify_migration` doesn't work

**Severity:** Medium (documented in CLAUDE.md but broken).
**Files:** `./run`, `CLAUDE.md`.

`CLAUDE.md` documents:

```
# Verify post-migration record counts and relational integrity
./run script verify_migration
```

But the `./run` script implements `script` as:

```bash
if [[ "$COMMAND" == "script" ]]; then
    echo "Running script"
    python "scripts/actions/$RESOURCE.py"
    exit 0
fi
```

It always looks in `scripts/actions/`. The verifier lives at
`scripts/tests/verify_migration.py`, so the call fails with
`can't open file '…/scripts/actions/verify_migration.py'`.

Same applies to `order_constraints.py`.

### Fix

Either:
- Search `scripts/actions/` then `scripts/tests/` (or use `find`), or
- Add a dedicated subcommand like `./run test verify_migration` that
  looks in `scripts/tests/`, or
- Move the verifiers into `scripts/actions/` (they're really one-off
  scripts, not unit tests).

While in there, the `script` subcommand has no usage / no error
message if `$RESOURCE` is empty.
