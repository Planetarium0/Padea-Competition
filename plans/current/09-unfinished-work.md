# Unfinished Work

What was designed but isn't built yet, and obvious next steps. This is
forward-looking — for *current bugs* see `plans/problems/`.

## Planned but unbuilt

### Scheduled cron triggers
Both ordering scripts are documented as "Wed 8 PM" and "Thu 3 PM" but
nothing runs them automatically. Today they need a human at the keyboard.

Options: systemd timer, cron, GitHub Actions on a schedule, or an Airtable
automation that pings a deployed endpoint.

### Live hosting for the webapp
Currently local-only. The hard parts are:
- A real public URL (so QR codes can encode `https://meals.padea.com.au/...`
  and work outside the school's network).
- A non-personal API key (the committed one is a developer's PAT).
- Some form of rate limiting or write-scoped key to make leaking less
  catastrophic.

### Actually sending email from `send_orders.py`
The script queues `Scheduled Emails` rows. The corresponding Airtable
automation that watches `Status='Queued'` and does the real send doesn't
exist yet (or at least isn't in this repo). Without it, queued emails
sit forever.

### Quality dashboard for caterer ratings
Originally part of the plan: a rollup on `Caterers` averaging the last
4 weeks of `Caterer Feedback`, with an automation alert if the score
drops below 3.0. Tables and feedback collection exist; the dashboard
doesn't.

### Last-week fallback
The revised emailing plan called for: "if no preference set, reuse the
student's pick from previous equivalent sessions before falling back to
AI assignment." `register_orders.py` doesn't do this — non-respondents
go straight to variety / popularity assignment.

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

### Authenticate the webapp
Today a student picks their own name. Trust comes from the in-person
context (the manager is right there). For a remote-friendly version,
either:
- Email a personalised link with the student's record ID encoded.
- Use Airtable's `?key=` with one-time write tokens.
- Adopt a real auth layer (overkill for the volume).

### Track changes to enrolment without a re-migration
Right now adding a student means editing Airtable directly. Adding a
*re-runnable, non-destructive* migration mode would help — diff against
existing records and only insert deltas.

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
preserving caterer/menu setup. There's no scripted path for this — and
the migration scripts can't be trusted to do it (they'd also wipe the
preserved tables).
