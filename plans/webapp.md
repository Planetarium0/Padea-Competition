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

A copy of this prompt is given under `plans/webapp.md`.

