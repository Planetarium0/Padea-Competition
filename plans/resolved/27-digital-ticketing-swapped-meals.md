# Problem: Swapped Meals Cause Classroom Confusion and Waste

## Context
When the backend ordering engine (`register_orders.py`) runs on Wednesday, it satisfies caterer-specific minimum-quantity rules (e.g., "must order at least 5 portions of any selected meal type"). To satisfy this rule, the engine will perform a "proportional swap" – automatically moving students off low-volume meals to more popular compatible items. 

Additionally, if a student does not scan the QR code to submit a preference by the Wednesday cutoff, they are assigned a default fallback meal (last week's choice or a popularity-weighted recommendation).

Today, these boxes are delivered unnamed (no student name tags on boxes).

## Problem Description
This process introduces two critical issues:
1. **Unaware Swaps:** A student who actively voted for a meal will arrive at the tutoring session next week completely unaware that their choice was forcefully swapped by the backend agent. They will try to grab their original choice from the table.
2. **Line Chaos with Unnamed Boxes:** Because the boxes are unnamed, a student who forgot to scan the QR code (or whose choice was swapped) might grab a meal they *think* they want (e.g., Sushi), thereby depriving a student who *actually* successfully voted for that specific meal. The first-come-first-served lunch rush completely undermines the integrity of the voting system and safety of dietary restrictions.

## Proposed Solution (AI Actionable)
Implement a **"Digital Ticketing" system** inside the webapp:

1. **Backend Integration:**
   When `register_orders.py` finalizes the weekly order, it creates `Orders` records in Airtable linking the specific students to their finalized assigned meal for that week's date.

2. **Webapp Landing Page Ticket (`webapp/app.js`):**
   - When a student scans the QR code on Tuesday and selects their name from the dropdown, the webapp should execute a query to Airtable to fetch that student's **finalized, assigned meal record for today's date**.
   - Before showing the feedback or preference form, display a prominent **"Meal Ticket" banner** at the top of the viewport:
     > 🍱 **Your Meal for Today: [Finalized Meal Name]**
     > *Note: If this doesn't match your vote, your choice was automatically swapped to satisfy catering limits / dietary safety.*
   - If the student has a registered dietary requirement, highlight it on the ticket in red/amber (e.g., `⚠️ GLUTEN FREE TICKET`).

3. **Operational "Line Pass" Workflow:**
   - The on-site manager no longer needs to print a paper roster or guess who ordered what.
   - The manager instructs students: *"Open the webapp, select your name, and show me your screen to pick up your box."*
   - The student's phone screen acts as a physical digital ticket in the lunch line. The manager hands over the matching unnamed box. 
   - This ensures students whose choices were swapped grab the correct fallback box, and dietary-restricted students are handed their safe priority boxes first.
