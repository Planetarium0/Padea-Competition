# 1st Iteration

Could you entirely overhaul the webapp given in the `webapp` directory?
You can safely disregard the majority of the content under the existing implementation of the webapp - the only thing you can keep is `config.env.js`, which contains the API keys for the Airtable database. You can view the Airtable schema through `scripts/schema.py`.
If implementing the webapp requires changes to the schema, let me know.

The function of the webapp you will implement is to act as a form for students to provide feedback on their caterer, the meals, and submit their preferences for next week's meal.
The webapp should take two url parameters:
- `session` - the sessionID for the current tutoring session. Required.
- `student` - the studentID of the student taking the form. Optional - if a student wants a personalized QR code to keep for themselves they'll use this.

The webapp will be eventually hosted live, but for now it'll be tested locally.

The actual form should be structured as follows:
- A "How was today's meal" field - 1-5 star rating.
- If 1-3 stars, another field (conditional, also optional) pops up: "What went wrong? (e.g., cold, small portion, didn't like taste)"
- And a "Change your current meal preference" selection menu - either in place, in a dropdown, in a popup modal, or in a new page - whatever makes the most sense. The current preferred meal should be pre-selected. The list of meals is just the current caterer's menu filtered to match the student's dietary requirements (i.e., any meal that has at least all the dietary requirements listed on the student, so that a non-dairy person can also eat vegetarian non-dairy items as well).

The form can have a little footnote that mentions the purpose of the form, i.e., "The meal ratings us help pick caterers in the future" or something.

When the webapp is accessed without any way to identify the student, they will need to find their name from a list of students in the current session before the form is shown to them.
Once a student is realized in a webapp, the webapp should remember them (ideally through cookies), so that they don't have to select their name every time.

The new form system should have a light color scheme with red as a primary color (`#A51C30`).
Airtable queries seem a little latent so you should cache where appropriate, and make wise API calls.
For example, instead of querying for the list of students and then filtering by session, you can just directly get the `Students` field of the current session.
Where possible, elements should be loaded instantly with airtable queries in the background.
Submission of the form should also write to the Airtable Database, provided changes were made or ratings were given.

For example, a vegan student accessing the webapp for the first time might look like this:
- Student scans the QR code, the webapp opens.
- Student sees "Who are you?", a field to search for their name, and a loading animation (representing the list of students for the session)
- The list of students loads and the student can either start typing their name in to search their name or scroll the list and find it manually.
- Once the student taps their name, they see the form pop up.
- They choose not to give a rating, and just click on "Change your current meal preference"
- Since the list of meals was loaded in the background, the user does not see a loading screen, and immediately see a list of vegan meals to choose from.
- The user selects their preferred meal, which takes them back to see the original form, and then hits submit.
- The user sees some sort of visual cue that the submit went through.

# 2nd Iteration

A few caveats - there's a dietary requirement called "Opted out of Catering" that you need to account for.
If this is the case you should prevent the user from submitting their review or preferences.

Furthermore, I think it's best to "soft-hide" the meals that don't match dietary requirements.
Students that are listed as vegan can still see non-vegan meals, but they will be below all compatible meals and grayed out, but still selectable.
They should also have text below or next to them indicating why they are incompatible (i.e., "May contain Red Meat" or "Contains Shellfish")
If they attempt to select such an option, there should be a popup confirming that they want to select this option.

I also think the current method for getting the meals is broken. Whatever student I select, it fails to show any meals from the caterer.
Can you verify the current system actually fetches the caterer? Once you have the caterer, you should easily be able to get to the menu items through the "Menu Items" field.
If you can't verify it yourself add console logging so I can verify myself.

# 3rd Iteration

I think fully implementing this will require major database architecture changes. I've listed them below:
- Students Table: Include a field for the meal preference, and remove the `Meal Selection` table from the schema. Since each student has a single preference, this replaces the need for a separate massive "Meal Selection" table, simplifying data retrieval.
- Orders Table: Its primary purpose is to store historical data (who ate what on which date) for feedback/accountability purposes, as well as acting as the primary source for upcoming selections. 
- Dietary Restrictions (Lookup) Table: Implement a table recording all the dietary restrictions. It'll also define the hierarchy of needs (e.g., mapping "Vegetarian" as a subset of "No Red Meat"). This allows the application to programmatically determine if a dish meets a student's constraints even if tags are not explicitly shared. It should have three columns, one for getting dietary restriction supersets (e.g., "No Shellfish" as a superset of "Vegeterian") and subsets - of which one is a backlink of the other. Since these relationships will be essentially hard-coded, store them in a python file and make a migration file `migrations/dietary_restrictions.py`.
- You will need to modify all the dietary requirement fields (in students and in menu items) from being `multipleSelects` to references to the relevant dietary restriction.

These changes to the database will require changes to `scripts/schema.py` and some of the migrations under `migrations/*.py`, and potentially other places as well.

The new webapp workflow involves intelligent filtering. Implement a filter logic that queries the Dietary Restrictions table. If a student has a "No Red Meat" constraint, the frontend must display all items labeled "Vegetarian" or "Pescatarian" based on the established "Is-A" subset relationships. Items with ambiguous ingredients must be displayed with a "May Contain" caution flag.

Furthermore, the preferences are copied, orderd, and recorded in the Orders table every Wednesday at 8:00 PM. If it's past this time, you can add a note (maybe a footnote, it doesn't really matter) that next week's orders have already been placed and that your preference will only affect the week after's meal. 

A copy of this prompt is given in `plans/webapp_revisions.md` under the "3rd Iteration" header

