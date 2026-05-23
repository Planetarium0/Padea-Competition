# Graph Report - .  (2026-05-23)

## Corpus Check
- Corpus is ~30,856 words - fits in a single context window. You may not need a graph.

## Summary
- 216 nodes · 290 edges · 22 communities (19 shown, 3 thin omitted)
- Extraction: 86% EXTRACTED · 14% INFERRED · 0% AMBIGUOUS · INFERRED: 41 edges (avg confidence: 0.9)
- Token cost: 12,500 input · 3,800 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Student Webapp & QR System|Student Webapp & QR System]]
- [[_COMMUNITY_Meal Resolution & Order Generation|Meal Resolution & Order Generation]]
- [[_COMMUNITY_Data Migration Pipeline|Data Migration Pipeline]]
- [[_COMMUNITY_Dietary Requirements Data|Dietary Requirements Data]]
- [[_COMMUNITY_Business Logic & System Overview|Business Logic & System Overview]]
- [[_COMMUNITY_Caterer Directory|Caterer Directory]]
- [[_COMMUNITY_Design Decisions & Rationale|Design Decisions & Rationale]]
- [[_COMMUNITY_LLM Extraction & Heuristic Parsers|LLM Extraction & Heuristic Parsers]]
- [[_COMMUNITY_Order Email Dispatch|Order Email Dispatch]]
- [[_COMMUNITY_Schema Architecture|Schema Architecture]]
- [[_COMMUNITY_Absence Records|Absence Records]]
- [[_COMMUNITY_School Exclusion Records|School Exclusion Records]]
- [[_COMMUNITY_Claude Settings|Claude Settings]]
- [[_COMMUNITY_QR Code Instance|QR Code Instance]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 21|Community 21]]

## God Nodes (most connected - your core abstractions)
1. `generate_orders()` - 15 edges
2. `airtable_get()` - 14 edges
3. `airtable_post()` - 11 edges
4. `support.py — Shared Support Module (imported as s)` - 11 edges
5. `loadSessionData()` - 8 edges
6. `process_orders()` - 8 edges
7. `students.py — Students Migration with Dietary Mapping` - 8 edges
8. `resolve_student_meal()` - 7 edges
9. `clear_table()` - 7 edges
10. `ask_llm()` - 7 edges

## Surprising Connections (you probably didn't know these)
- `atFetch()` --semantically_similar_to--> `airtable_get()`  [INFERRED] [semantically similar]
  output/webapp/app.js → scripts/support.py
- `atPost()` --semantically_similar_to--> `airtable_post()`  [INFERRED] [semantically similar]
  output/webapp/app.js → scripts/support.py
- `is_item_compatible()` --semantically_similar_to--> `isItemCompatible()`  [INFERRED] [semantically similar]
  scripts/generate_orders.py → output/webapp/app.js
- `QR Code → Session-Scoped Webapp URL Pattern` --conceptually_related_to--> `app`  [INFERRED]
  scripts/generate_qr.py → output/webapp/app.js
- `LLM-with-Heuristic-Fallback Pattern` --rationale_for--> `ask_llm()`  [INFERRED]
  migrations/students.py → scripts/support.py

## Hyperedges (group relationships)
- **Full Migration Pipeline: PDF Cache → Parse (LLM/Heuristic) → Airtable Post** — scripts_cache_pdf_cache_pdf, scripts_support_ask_llm, scripts_support_airtable_post [INFERRED 0.85]
- **Order Generation Flow: Resolve Meals → Enforce Min Qty → Write to Airtable → Format Email** — scripts_generate_orders_resolve_student_meal, scripts_generate_orders_enforce_min_qty, scripts_generate_orders_write_orders_to_airtable, scripts_send_orders_format_email [INFERRED 0.85]
- **Student Interaction Loop: QR Scan → Webapp → Select Meal + Rate → Informs Next Order** — scripts_generate_qr_main, webapp_app_selectmeal, webapp_app_submitrating, scripts_generate_orders_resolve_student_meal [INFERRED 0.75]
- **Catering Pipeline: Student Selection → Order Engine → Caterer Email** — webapp_index_spa, plans_impl_plan_ai_gap_filling, concept_caterer_email_format [EXTRACTED 0.95]
- **Caterer Data Flow: PDF → Cache → Airtable** — resources_caterer_menus_pdf, cache_caterer_menus_lakehouse, converted_caterers_lakehouse [EXTRACTED 0.95]
- **Order Validation: Dietary + Min Qty + Fallback Logic** — plans_impl_plan_dietary_filtering, plans_impl_plan_min_qty_enforcement, plans_impl_revised_fallback_logic [INFERRED 0.85]

## Communities (22 total, 3 thin omitted)

### Community 0 - "Student Webapp & QR System"
Cohesion: 0.09
Nodes (28): Dietary Compatibility Filter (Positive + Negative Requirements), QR Code → Session-Scoped Webapp URL Pattern, is_item_compatible(), Check if a menu item is compatible with a student's dietary requirements., generate_qr(), main(), make_session_url(), generate_qr.py — Generate QR code PNGs for each session's web app URL.  Each QR (+20 more)

### Community 1 - "Meal Resolution & Order Generation"
Cohesion: 0.10
Nodes (27): 3-Step Meal Resolution: Explicit Selection → Previous Week → AI Assigned, ai_assign_meal(), build_lookups(), determine_round(), enforce_min_qty(), find_previous_selection(), generate_orders(), get_next_week_monday() (+19 more)

### Community 2 - "Data Migration Pipeline"
Cohesion: 0.17
Nodes (23): dietary_mappings.json — Dietary String Translation Cache, Clear-Parse-Link-Post Migration Pattern, Two-Pass Schema Creation (Resolves Circular Links), absences.py — Absences Migration, caterer_contacts.py — Caterer Contacts Migration, caterer_menus.py — Caterer Menus Migration, caterers.py — Caterers & Schools Migration, exclusions.py — Exclusions Migration (+15 more)

### Community 3 - "Dietary Requirements Data"
Cohesion: 0.11
Nodes (18): Dairy Free, Gluten Free, Gluten Free, Dairy Free, Halal, Halal, Vegetarian, No Beef, No Beef, No Pork, No Fish (+10 more)

### Community 4 - "Business Logic & System Overview"
Cohesion: 0.11
Nodes (19): Padea Project Overview, Caterer Order Email Format (per session, school, delivery), QR Code Session URL Pattern (meals.padea.com.au/s/{id}), Minimum Order Quantity Enforcement Logic, n8n Order Email Workflow, Order Line Items Table Schema, Automated Catering Pipeline System Overview, Weekly Orders Table Schema (+11 more)

### Community 5 - "Caterer Directory"
Cohesion: 0.13
Nodes (18): Guzman y Gomez Contact: Big Chicken + Medium Giraffe, Kenko Sushi House Contact: Big Mom (contact + chef), Lakehouse VP Contact: Carmen Gabrielle, Terrific Noodles Contact: Dylan + James Chern, Guzman y Gomez Menu, Kenko Sushi House Menu, Lakehouse Victoria Point Menu, Terrific Noodles Menu (+10 more)

### Community 6 - "Design Decisions & Rationale"
Cohesion: 0.14
Nodes (14): Dietary Legend (GF, DF, NF, VO + Halal rule), LLM Fallback Behaviour (Claude API vs heuristics), Dietary Tag System (GF, DF, NF, VO, Halal, No Beef, No Pork, etc.), Upsert Pattern for Meal Selections (overwrite on re-scan), AI Gap-Filling Scoring Function for Non-Respondents, Dietary Compatibility Filtering Logic, No Authentication Rationale (low-stakes in-person interaction), Feedback-Driven Quality Monitoring (Airtable) (+6 more)

### Community 7 - "LLM Extraction & Heuristic Parsers"
Cohesion: 0.15
Nodes (7): LLM-with-Heuristic-Fallback Pattern, clean_school_names(), parse_contacts_heuristic(), Fallback high-fidelity parser for caterer contacts using regex/heuristics., parse_menus_heuristic(), parse_exclusions_heuristic(), map_dietary_heuristically()

### Community 8 - "Order Email Dispatch"
Cohesion: 0.27
Nodes (9): format_email(), load_draft_orders(), load_order_details(), process_orders(), send_orders.py — Format and log caterer order emails.  Reads Weekly Orders with, Process all draft orders., Load all Weekly Orders with Status=Draft., Load all related data for a single Weekly Order. (+1 more)

### Community 9 - "Schema Architecture"
Cohesion: 0.50
Nodes (4): Migration Dependency Order, Migration Pattern (clear/parse/llm/link/post), Normalized Relational Schema Design (10 tables), Two-Pass Schema Creation (resolves circular links)

### Community 10 - "Absence Records"
Cohesion: 0.50
Nodes (4): Absences: ISHS 02/05/2026 (Charlie Morris, Jack Carter, Charlie Mitchell), Absences: JPC 02/05/2026 (Christina Hu, Nathan Smith), Absences: MBBC 02/05/2026 (Noah Baker), Absences PDF (source resource)

### Community 11 - "School Exclusion Records"
Cohesion: 0.50
Nodes (4): Exclusion: CHAC School Camp (Years 12, 10), Exclusion: ISHS Open Day (all year levels), Exclusion: Loreto College Parent Teacher Interviews, Exclusions PDF (source resource)

### Community 14 - "QR Code Instance"
Cohesion: 1.00
Nodes (3): QR Code - Moreton Bay Boys' College (2026-05-02), Moreton Bay Boys' College, Tutoring Session - Moreton Bay Boys' College 2026-05-02

## Knowledge Gaps
- **51 isolated node(s):** `Halal`, `Opted out of Catering`, `No Beef, No Pork`, `Gluten Free`, `No Pork, No Shellfish` (+46 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **3 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `airtable_get()` connect `Data Migration Pipeline` to `Order Email Dispatch`, `Meal Resolution & Order Generation`, `Student Webapp & QR System`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Why does `generate_orders()` connect `Meal Resolution & Order Generation` to `Order Email Dispatch`, `Data Migration Pipeline`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `support.py — Shared Support Module (imported as s)` connect `Data Migration Pipeline` to `Order Email Dispatch`, `Meal Resolution & Order Generation`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **What connects `Halal`, `Opted out of Catering`, `No Beef, No Pork` to the rest of the system?**
  _82 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Student Webapp & QR System` be split into smaller, more focused modules?**
  _Cohesion score 0.08571428571428572 - nodes in this community are weakly interconnected._
- **Should `Meal Resolution & Order Generation` be split into smaller, more focused modules?**
  _Cohesion score 0.10317460317460317 - nodes in this community are weakly interconnected._
- **Should `Dietary Requirements Data` be split into smaller, more focused modules?**
  _Cohesion score 0.10526315789473684 - nodes in this community are weakly interconnected._