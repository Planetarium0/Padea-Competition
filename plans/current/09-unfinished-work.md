# Unfinished Work

What was designed but isn't built yet, and obvious next steps. This is
forward-looking — for *current bugs* see `plans/problems/`.

## Planned but unbuilt

### Scheduled cron triggers
Both ordering scripts are documented as "Wed 8 PM" and "Thu 3 PM" but
nothing runs them automatically. Today they need a human at the keyboard.
The caterer evaluator (`evaluate_caterers.py`) is also manual.

Options: systemd timer, cron, GitHub Actions on a schedule, or an Airtable
automation that pings a deployed endpoint.

### Live hosting for the webapp
Currently local-only. The webapp itself no longer ships a token (the
Python proxy holds the Airtable key server-side), so the remaining gaps
are infrastructure rather than security-on-the-client:

- A real public URL (so QR codes can encode `https://meals.padea.com.au/...`
  and work outside the school's network).
- A hosted Python runtime (or a port of `host_webapp.py` / `api.py` to a
  serverless platform).
- The `AIRTABLE_API_KEY` rotated and stored in the host's secret manager.

### Actually sending email
Every email pathway (`send_orders.py`, `send_meals_links.py`,
`send_qr_emails.py`, `evaluate_caterers.py`) writes `Scheduled Emails`
rows with `Status='Queued'`. The corresponding Airtable automation that
watches `Status='Queued'` and does the real send doesn't exist in this
repo (it's configured in Airtable directly). Without it, queued emails
sit forever.

### Idempotency for outbound emails
None of the email-queuing scripts check for existing rows before
inserting. Running `./run orders send` twice queues two copies of every
email. The webapp's feedback path goes through a real upsert; the
back-end scripts don't.

### Quality dashboard for caterer ratings
`evaluate_caterers.py` queues watch/switch alerts directly, so the
"flag a declining caterer" loop is closed. A visual dashboard (rolling
averages per caterer, trend lines, term-over-term comparison) is still
unbuilt — the data exists, the chart doesn't.

### Caterer email format A/B with the coordinator
The current markdown format is one redesign. The original brief noted
that the program coordinator may have habits — comparing a generated
email side-by-side with one they wrote manually is on the checklist
but not yet done.

### Year-level-aware exclusion exits
`Exclusions.Affected Year Levels` already accepts specific year levels,
but the parser sometimes captures odd values. Spot-check the LLM output
periodically.

## Plausible next iterations

### Track changes to enrolment without a re-migration
Right now adding a student means editing Airtable directly. Adding a
*re-runnable, non-destructive* migration mode would help — diff against
existing records and only insert deltas. Same applies to mid-term menu
edits (where a clear-and-reinsert breaks every `Meal Preference` link).

### Surface caterer rating + popularity inside the webapp
"Most students picked X last week" or "current caterer is averaging 4.2
stars" — both available from the data, neither shown.

### Multi-meal orders
Some events (e.g. exam weeks) might want two boxed meals per student,
or a special menu. Not in scope today.

### Calendar export
A term-long .ics of every session per school, exported from `Sessions`,
would help the program coordinator.

### A "next term" reset workflow
At term boundaries someone will need to wipe last term's data while
preserving caterer/menu setup. `clear_database.py` exists but is
all-or-nothing; there's no scripted path that preserves a subset.

### Rich text / image support in caterer emails
Currently restricted to the Markdown subset Airtable's send-email
action supports. A move to a real SMTP-backed sender (see "Actually
sending email") opens up tables, attachments, and signed-PDF order
forms.
