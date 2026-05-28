# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project does

This project is part of a larger set of projects aimed at fixing bottlenecks in a tutoring business (Padea).
Schools partner with Padea to run weekly, small-group tutoring sessions on their campus after hours. Families enrol at the start of each term, so largely the same students attend every session that term (ignoring absences and rare mid-term enrolments). Each session includes a restaurant-catered dinner break in the middle.
Padea contracts external caterers to cook and deliver individually boxed meals (one per student) to each session. The order should arrive 5–10 minutes before the dinner break so the on-site manager can set up the meals with the delivery driver’s help.
The on-site manager may collect feedback and share it with us. The on-site manager is usually the same on a given day at a given school each week (e.g. Mondays at ACME School), though this can change on one-off occasions. The caterer may contact the on-site manager’s mobile to confirm arrival, report being late, or ask for help finding the
session location (building and room).
Each Thursday, our program coordinator emails each caterer an order for the following week’s meals, picking a few items off the caterer’s menu and making an educated guess at the best meals and quantities of each meal.
Students often tell us the selected meals don’t match their taste preferences. Food quality also tends to decline over time with each caterer. Ordering meals is tedious for the program coordinator – and will become a bottleneck for the business.

This project is aimed at fixing this bottleneck - solving the problem from order to delivery.

The current state of the project is stored in `plans/current/*.md`, and you should defer to that for up-to-date information on the current state of the project.
Another critical file is `data/schema.py`, which represents the schema for the Airtable database.

## Python scripting

You are building on an arch linux system with an externally managed environment. If installing packages with pip you must use the system package manager or install locally with `pip install --user --break-system-packages [package]`

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
