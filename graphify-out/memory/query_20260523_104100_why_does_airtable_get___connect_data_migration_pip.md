---
type: "query"
date: "2026-05-23T10:41:00.400466+00:00"
question: "Why does airtable_get() connect Data Migration Pipeline to Order Email Dispatch, Meal Resolution & Order Generation, Student Webapp & QR System?"
contributor: "graphify"
source_nodes: ["scripts_support_airtable_get"]
---

# Q: Why does airtable_get() connect Data Migration Pipeline to Order Email Dispatch, Meal Resolution & Order Generation, Student Webapp & QR System?

## Answer

airtable_get() in scripts/support.py is the single shared abstraction for all Airtable reads across the codebase. Migration scripts use it to fetch already-inserted records for linking, generate_orders.py uses it to load student/menu/session data, send_orders.py uses it to load draft orders, and the webapp uses it indirectly via the Airtable REST API. Its high betweenness centrality reflects that every feature depends on reading from Airtable.

## Source Nodes

- scripts_support_airtable_get