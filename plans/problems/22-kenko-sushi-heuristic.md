# 22 — Heuristic contact parser still misses Kenko Sushi House

**Severity:** Low (documented; only affects no-API-key runs).
**File:** `scripts/migrations/caterer_contacts.py`,
`parse_contacts_heuristic`.

`plans/old/migration/walkthrough.md` notes this:

> Kenko Sushi House's contact name field was not populated by the
> heuristic parser. The source text uses "Big Mom (main point of
> contact and chef)" which the LLM parser handles correctly but the
> fallback regex misses.

There is a partial fix in the heuristic — it does set chef_name and
chef_email after detecting "main point of contact and chef" — but
that block runs **after** the line-iteration loop where contact_name
should have been picked up. The contact_name lookup uses the
`contact for orders` substring which doesn't appear in the Big Mom
block.

End result: with no API key, Kenko Sushi House ends up with:
- Contact Email set (matches the first email in the block)
- Chef Name/Email set (from the post-loop block)
- Contact Name **blank**

### Fix

Add a parallel branch in the heuristic: if a line matches
`^([^(]+?)\s*\(.*(main point of contact|main contact|primary contact)`,
take the captured prefix as contact_name. Then the existing "and chef"
block copies it into chef_name.
