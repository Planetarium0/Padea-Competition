# Business Context

## What Padea does

Padea is a tutoring business operating in partnership with high schools around
Brisbane. The model:

- Schools host weekly small-group tutoring sessions on their own campus after
  school hours.
- Families enrol at the start of each term. The roster is largely static for
  the term — the same students attend every week, give or take occasional
  absences and rare mid-term enrolments.
- Each session runs long enough to include a dinner break in the middle.
- Padea contracts an external caterer to cook and deliver individually-boxed
  meals (one per attending student) for each session.
- An on-site manager (a Padea employee, usually the same person at each
  school each week) receives the delivery, sets up dinner, and is the
  caterer's contact if anything goes wrong.

## The roster of schools

Six schools, three regions:

| Region | Schools |
|---|---|
| Redlands | Moreton Bay Boys' College |
| South Brisbane | John Paul College, MacGregor State High School |
| West Brisbane | Indooroopilly State High School |
| Central Brisbane | Loreto College, Cannon Hill Anglican College |

(A fourth region "Central Brisbane" appears in `Schools.Region` choices for
two schools.)

## The caterers

Four contracted caterers, each serving one or two of the schools today, with
some flexibility ("Able to Serve" but not currently serving). Each caterer has:

- A flat per-item price across their whole menu (Padea pays one rate
  regardless of which item is chosen).
- A delivery fee, charged either **per trip** or **per school per trip**.
- A minimum-quantity rule: when ordering N distinct items from them, every
  item must hit a per-item minimum (`Min Qty 4/5/6 Items` fields).
- A menu of ~10 items, each with inline dietary codes (GF, DF, NF, VO).

The "Big Mom" caterer (Kenko Sushi House) is a single person who is both
contact and chef — the parser has to detect this special case.

## The on-site managers

Usually one manager per school per day. The manager:

- Greets the caterer's delivery driver 5–10 minutes before the dinner break.
- Helps set up boxed meals.
- Fields any "running late" / "where exactly is the room" calls from the
  caterer at their personal mobile.
- Occasionally collects ad-hoc feedback from students.

The same person typically covers a given school on a given weekday for the
whole term, but this can change for one-offs.

## The bottleneck this project fixes

> Every Thursday, the program coordinator manually emails each caterer an
> order for the following week's meals. They pick a few items off the menu
> and guess at quantities.

Three problems:

1. **Students dislike the picks.** They never get a choice; the coordinator
   guesses what they'd want.
2. **Food quality silently drifts.** No structured feedback loop exists to
   catch a caterer whose quality is declining.
3. **It's tedious and won't scale.** Adding schools or caterers makes the
   Thursday email session linearly longer. The coordinator is the
   single point of failure.

## What "fixed" looks like

Students choose their own meals via a QR code at their session; non-respondents
get smart fallbacks (last week's pick → AI-assigned). The system compiles the
weekly order, validates dietary and minimum-quantity constraints, and emails
the caterer in a structured format. The coordinator only steps in when
something looks off.

A secondary win: ratings collected through the same form feed a quality
score that flags declining caterers.
