# 32 — `host_webapp.py` startup hints point at the old `./run qr` command

**Severity:** Low (cosmetic; misleads operators following the on-screen instructions).
**File:** `scripts/actions/host_webapp.py`.

```python
"""
After starting, generate matching QR codes with:
    ./run qr --origin http://<printed-ip>:<port>
"""
...
print(f"Generate QR codes for this server:")
print(f"  ./run qr --origin {origin}")
```

The actual command is `./run forms qr --origin …` (`./run qr` doesn't
exist). An operator copy-pasting the printed line gets an unhelpful
`[ERROR] Unknown command: qr`.

The same `index.html` reference appears in the prints at startup —
the actual entry path is `meals.html`.

### Fix

Replace both occurrences (docstring + `print`) with the current
command, and update the local/network URL prints to point at
`meals.html?session=…` (or, since that needs a session id, drop the
specific path and just print the origin).
