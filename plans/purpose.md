# Summary

This project is part of a larger set of projects aimed at fixing bottlenecks in a tutoring business (Padea).
Schools partner with Padea to run weekly, small-group tutoring sessions on their campus after hours. Families enrol at the start of each term, so largely the same students attend every session that term (ignoring absences and rare mid-term enrolments). Each session includes a restaurant-catered dinner break in the middle.
Padea contracts external caterers to cook and deliver individually boxed meals (one per student) to each session. The order should arrive 5–10 minutes before the dinner break so the on-site manager can set up the meals with the delivery driver’s help.
The on-site manager may collect feedback and share it with us. The on-site manager is usually the same on a given day at a given school each week (e.g. Mondays at ACME School), though this can change on one-off occasions. The caterer may contact the on-site manager’s mobile to confirm arrival, report being late, or ask for help finding the
session location (building and room).
Each Thursday, our program coordinator emails each caterer an order for the following week’s meals, picking a few items off the caterer’s menu and making an educated guess at the best meals and quantities of each meal.
Students often tell us the selected meals don’t match their taste preferences. Food quality also tends to decline over time with each caterer. Ordering meals is tedious for the program coordinator – and will become a bottleneck for the business.

You need to come up with a real world plan to fix this bottleneck.
There have been some proposed partial solutions you may or may not want to consider:
- The email(s) sent each Thursday for next week's meals will be automated by AI.
- Students can give feedback on meals and choose what they want for next week via a QR code during their meal break.

You will need to consider factors like dietary requirements, pricing, which caterers can go to which schools, the minimum order quantity for caterers (*), etc. *order quantity means total number of ordered meals for the week across all schools.

You can request access to other automation and scripting tools such as n8n, though they may have to be set up.

Currently, the new proposed system should be in the testing phase, so no emails should actually get sent to caterers - in other words the project should have no external impact yet.
