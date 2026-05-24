Every Wednesday at 8:00 PM, a script, `scripts/register_orders.py`, should run.
The script should register all the orders by doing the following:
For all students recieving tutoring for next week's session, keeping in mind absences and exclusions, their preferred meal should be recorded in the `Order` table.
In doing so, it'll need to verify that all students have picked from the menu of the session's caterer.
That is, given `session`, the program should check `session -> student -> preferred meal -> caterer == session -> caterer`.
If the student does not have a preferred meal set, then set their meal according to dietary requirements and popularity of other meals (as specified later).
The date should be set in the future for when next week's session is.
The script should also verify that the caterer's constraints (such as "Min Qty 4 Items") are not violated.
If they are, find some the least-ordered items, and swap them for other more-popular items until you get a valid state.
When setting or swapping new meals, dietary requirements *must* be followed. The only exception is if the student explicitly set their preference to a particular meal - in which case that particular meal only becomes an exception. If there is no other alternative that follows dietary requirements, you may have to swap out some of the more popular items.
Apart from that constraint, swapping should be proportional to the existing orders. That is, if there are 10 Burgers, 5 Sandwiches, and 3 other meals that you need to swap,
2 of those meals should be swapped for Burgers and 1 of those meals for sandwiches. This constraint is not as important.

Then, every Thursday afternoon at 3:00 PM, another script `script/send_orders.py` should run.
It'll take all the orders for next week's sessions and send them to their respective caterers, taking into account whether the Chef wants to be cc'd.
This script already exists, but you may need to entirely recreate it so that it works with the new database layout.
For now, the script does not actually need to send an email. Just create a fake `send_email` function that does not actually send the email and instead logs it to a file in `output/emails`.

You need to create these scripts. Currently, you don't need to implement the running of the scripts the particular times.
