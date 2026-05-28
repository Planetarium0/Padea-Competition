# Problem: Shared Dropdown Without Auth allows Student Pranks

## Context
The student-facing webapp is completely unauthenticated. It accepts a `?session=<session_id>` URL parameter and displays a list of all students enrolled in that session. A student selects their name from a dropdown, rates today's meal, and selects next week's meal. 

## Problem Description
High school students will play pranks. Because there is no check or authentication:
1. Student A can select Student B's name, submit a 1-star rating for their current meal (poisoning our quality ratings data), and change their next-week preference to a meal they hate or have an allergy to.
2. A single student can easily submit preferences on behalf of multiple classmates as a joke, breaking the integrity of the ordering metrics.

We want to avoid a complex authentication layer (passwords, emails, sign-ins) as this adds too much friction for high school students.

## Proposed Solution (AI Actionable)
Implement a **One-Way Roster Lockout ("Disappearing Dropdown")** pattern in `webapp/app.js`:

1. **Local Lockout:**
   Upon successful submission of the form, write a key to the browser's `localStorage` tracking that this device has submitted a preference:
   ```javascript
   localStorage.setItem('padea_submitted_' + sessionId, 'true');
   ```
   If this key exists when loading the page, hide the picker and show a banner: *"Thank you! Your preference has already been submitted for next week. If you need to make changes, please see the on-site manager."*

2. **One-Way Dropdown (Roster Filtering):**
   *When a student successfully submits their preference:*
   - In the Airtable submit payload, we save the preference.
   - For other students scanning the QR code: **any student who has already submitted a preference for next week should be removed from the dropdown list.**
   - *How to implement:* When loading the roster for the session, also fetch next week's `Meal Preference` or `Orders` state. If a student record already has their `Meal Preference` set for the upcoming term/week, filter them *out* of the dropdown select list so they cannot be selected again.
   - *Why this works:* A prankster student cannot change their friend's meal after the friend has already submitted, because the friend's name will no longer be in the dropdown. If they try to mess with their friend's name *before* the friend arrives, the friend will notice their name is missing upon trying to vote and immediately alert the manager, exposing the prank.
