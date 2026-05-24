A few caveats - there's a dietary requirement called "Opted out of Catering" that you need to account for.
If this is the case you should prevent the user from submitting their review or preferences.

Furthermore, I think it's best to "soft-hide" the meals that don't match dietary requirements.
Students that are listed as vegan can still see non-vegan meals, but they will be below all compatible meals and grayed out, but still selectable.
They should also have text below or next to them indicating why they are incompatible (i.e., "May contain Red Meat" or "Contains Shellfish")
If they attempt to select such an option, there should be a popup confirming that they want to select this option.

I also think the current method for getting the meals is broken. Whatever student I select, it fails to show any meals from the caterer.
Can you verify the current system actually fetches the caterer? Once you have the caterer, you should easily be able to get to the menu items through the "Menu Items" field.
If you can't verify it yourself add console logging so I can verify myself.

A copy of this prompt is given in `plans/webapp_revisions.md`

# Updated revisions
