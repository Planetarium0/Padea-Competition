# Graph Report - Padea  (2026-05-24)

## Corpus Check
- 34 files · ~32,892 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 396 nodes · 506 edges · 35 communities (28 shown, 7 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 41 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7ae196ff`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

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
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]

## God Nodes (most connected - your core abstractions)
1. `generate_orders()` - 15 edges
2. `airtable_get()` - 14 edges
3. `airtable_post()` - 11 edges
4. `support.py — Shared Support Module (imported as s)` - 11 edges
5. `atFetch()` - 9 edges
6. `cacheGet()` - 9 edges
7. `cacheSet()` - 9 edges
8. `Step-by-Step Migration` - 9 edges
9. `process_orders()` - 8 edges
10. `Migration Scripts` - 8 edges

## Surprising Connections (you probably didn't know these)
- `atFetch()` --semantically_similar_to--> `airtable_get()`  [INFERRED] [semantically similar]
  webapp/app.js → scripts/support.py
- `atPost()` --semantically_similar_to--> `airtable_post()`  [INFERRED] [semantically similar]
  output/webapp/app.js → scripts/support.py
- `QR Code → Session-Scoped Webapp URL Pattern` --conceptually_related_to--> `app`  [INFERRED]
  scripts/generate_qr.py → webapp/app.js
- `is_item_compatible()` --semantically_similar_to--> `isItemCompatible()`  [INFERRED] [semantically similar]
  scripts/generate_orders.py → output/webapp/app.js
- `LLM-with-Heuristic-Fallback Pattern` --rationale_for--> `ask_llm()`  [INFERRED]
  migrations/students.py → scripts/support.py

## Hyperedges (group relationships)
- **Full Migration Pipeline: PDF Cache → Parse (LLM/Heuristic) → Airtable Post** — scripts_cache_pdf_cache_pdf, scripts_support_ask_llm, scripts_support_airtable_post [INFERRED 0.85]
- **Order Generation Flow: Resolve Meals → Enforce Min Qty → Write to Airtable → Format Email** — scripts_generate_orders_resolve_student_meal, scripts_generate_orders_enforce_min_qty, scripts_generate_orders_write_orders_to_airtable, scripts_send_orders_format_email [INFERRED 0.85]
- **Student Interaction Loop: QR Scan → Webapp → Select Meal + Rate → Informs Next Order** — scripts_generate_qr_main, webapp_app_selectmeal, webapp_app_submitrating, scripts_generate_orders_resolve_student_meal [INFERRED 0.75]
- **Catering Pipeline: Student Selection → Order Engine → Caterer Email** — webapp_index_spa, plans_impl_plan_ai_gap_filling, concept_caterer_email_format [EXTRACTED 0.95]
- **Caterer Data Flow: PDF → Cache → Airtable** — resources_caterer_menus_pdf, cache_caterer_menus_lakehouse, converted_caterers_lakehouse [EXTRACTED 0.95]
- **Order Validation: Dietary + Min Qty + Fallback Logic** — plans_impl_plan_dietary_filtering, plans_impl_plan_min_qty_enforcement, plans_impl_revised_fallback_logic [INFERRED 0.85]

## Communities (35 total, 7 thin omitted)

### Community 0 - "Student Webapp & QR System"
Cohesion: 0.11
Nodes (19): Dietary Compatibility Filter (Positive + Negative Requirements), is_item_compatible(), Check if a menu item is compatible with a student's dietary requirements., apiKey(), app, atGetRecord(), atPatch(), atPost() (+11 more)

### Community 1 - "Meal Resolution & Order Generation"
Cohesion: 0.10
Nodes (27): 3-Step Meal Resolution: Explicit Selection → Previous Week → AI Assigned, ai_assign_meal(), build_lookups(), determine_round(), enforce_min_qty(), find_previous_selection(), generate_orders(), get_next_week_monday() (+19 more)

### Community 2 - "Data Migration Pipeline"
Cohesion: 0.12
Nodes (32): dietary_mappings.json — Dietary String Translation Cache, Clear-Parse-Link-Post Migration Pattern, Two-Pass Schema Creation (Resolves Circular Links), absences.py — Absences Migration, caterer_contacts.py — Caterer Contacts Migration, caterer_menus.py — Caterer Menus Migration, caterers.py — Caterers & Schools Migration, exclusions.py — Exclusions Migration (+24 more)

### Community 3 - "Dietary Requirements Data"
Cohesion: 0.11
Nodes (18): Dairy Free, Gluten Free, Gluten Free, Dairy Free, Halal, Halal, Vegetarian, No Beef, No Beef, No Pork, No Fish (+10 more)

### Community 4 - "Business Logic & System Overview"
Cohesion: 0.06
Nodes (33): Dietary Legend (GF, DF, NF, VO + Halal rule), LLM Fallback Behaviour (Claude API vs heuristics), Padea Project Overview, Caterer Order Email Format (per session, school, delivery), Dietary Tag System (GF, DF, NF, VO, Halal, No Beef, No Pork, etc.), QR Code Session URL Pattern (meals.padea.com.au/s/{id}), Upsert Pattern for Meal Selections (overwrite on re-scan), AI Gap-Filling Scoring Function for Non-Respondents (+25 more)

### Community 5 - "Caterer Directory"
Cohesion: 0.13
Nodes (18): Guzman y Gomez Contact: Big Chicken + Medium Giraffe, Kenko Sushi House Contact: Big Mom (contact + chef), Lakehouse VP Contact: Carmen Gabrielle, Terrific Noodles Contact: Dylan + James Chern, Guzman y Gomez Menu, Kenko Sushi House Menu, Lakehouse Victoria Point Menu, Terrific Noodles Menu (+10 more)

### Community 6 - "Design Decisions & Rationale"
Cohesion: 0.10
Nodes (35): atCreate(), atFetch(), atGet(), atList(), atUpdate(), cacheGet(), cacheSet(), clearKnownStudent() (+27 more)

### Community 7 - "LLM Extraction & Heuristic Parsers"
Cohesion: 0.15
Nodes (7): LLM-with-Heuristic-Fallback Pattern, clean_school_names(), parse_contacts_heuristic(), Fallback high-fidelity parser for caterer contacts using regex/heuristics., parse_menus_heuristic(), parse_exclusions_heuristic(), map_dietary_heuristically()

### Community 8 - "Order Email Dispatch"
Cohesion: 0.06
Nodes (30): Automated Tests, Automating Padea's Catering Pipeline, code:mermaid (flowchart LR), code:block2 (https://meals.padea.com.au/s/{session_airtable_id}), code:block3 (1. Determine "next week" date range (Mon–Fri of the followin), code:block4 (score(item, student) =), code:block5 (1. Cron Trigger: Thursday 09:00 AEST), code:block6 (Subject: Padea Meal Order — Week of 4 May 2026) (+22 more)

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

### Community 22 - "Community 22"
Cohesion: 0.08
Nodes (23): Automating Padea's Catering Pipeline (Revised), code:mermaid (flowchart LR), code:block2 (1. Determine ordering round (R1=Thu for Mon–Wed, R2=Sat for ), code:python (def resolve_meal(student, session, caterer_menu_items):), code:bash (./run orders generate          # compile orders for next rou), code:block5 (Subject: Padea Meal Order — Week of 4 May 2026 (Mon–Wed)), Decisions Made, File Summary (+15 more)

### Community 23 - "Community 23"
Cohesion: 0.10
Nodes (20): Automated Tests, code:mermaid (erDiagram), Implementation Plan - Migrating Padea Data to Airtable, Migration Scripts, [MODIFY] [absences.py](file:///home/daniel/Downloads/Padea/migrations/absences.py), [MODIFY] [caterer_contacts.py](file:///home/daniel/Downloads/Padea/migrations/caterer_contacts.py), [MODIFY] [caterer_menus.py](file:///home/daniel/Downloads/Padea/migrations/caterer_menus.py), [MODIFY] [caterers.py](file:///home/daniel/Downloads/Padea/migrations/caterers.py) (+12 more)

### Community 24 - "Community 24"
Cohesion: 0.11
Nodes (18): 1. Schema initialisation (`./run schema update`), 2. Caterers (`./run migrate caterers`), 3. Caterer contacts (`./run migrate contacts`), 4. Caterer menus (`./run migrate menus`), 5. Sessions (`./run migrate sessions`), 6. Students (`./run migrate students`), 7. Absences (`./run migrate absences`), 8. Exclusions (`./run migrate exclusions`) (+10 more)

### Community 25 - "Community 25"
Cohesion: 0.12
Nodes (15): Airtable record linking, Architecture, code:bash (# Migrate all resources), code:block2 (AIRTABLE_API_KEY=...), code:block3 (resources/*.xlsx + resources/*.pdf), code:block4 (caterers → caterer_contacts → caterer_menus), Commands, Core modules (+7 more)

### Community 26 - "Community 26"
Cohesion: 0.17
Nodes (11): Sheet: CHAC - Monday, Sheet: CHAC - Wednesday, Sheet: ISHS - Monday, Sheet: ISHS - Thursday, Sheet: ISHS - Tuesday, Sheet: JPC - Tuesday, Sheet: JPC - Wednesday, Sheet: LC - Monday (+3 more)

### Community 27 - "Community 27"
Cohesion: 0.47
Nodes (5): QR Code → Session-Scoped Webapp URL Pattern, generate_qr(), main(), make_session_url(), generate_qr.py — Generate QR code PNGs for each session's web app URL.  Each QR

### Community 28 - "Community 28"
Cohesion: 0.33
Nodes (5): Phase 1: Schema + Order Engine, Phase 2: Student Web App, Phase 3: Email + QR, Phase 4: Verification, Tasks

### Community 29 - "Community 29"
Cohesion: 0.50
Nodes (3): Answer, Q: Why does airtable_get() connect Data Migration Pipeline to Order Email Dispatch, Meal Resolution & Order Generation, Student Webapp & QR System?, Source Nodes

## Knowledge Gaps
- **140 isolated node(s):** `Halal`, `Opted out of Catering`, `No Beef, No Pork`, `Gluten Free`, `No Pork, No Shellfish` (+135 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **7 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `airtable_get()` connect `Data Migration Pipeline` to `Meal Resolution & Order Generation`, `Community 27`, `Design Decisions & Rationale`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `atFetch()` connect `Design Decisions & Rationale` to `Student Webapp & QR System`, `Data Migration Pipeline`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Why does `generate_orders()` connect `Meal Resolution & Order Generation` to `Data Migration Pipeline`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **What connects `Halal`, `Opted out of Catering`, `No Beef, No Pork` to the rest of the system?**
  _171 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Student Webapp & QR System` be split into smaller, more focused modules?**
  _Cohesion score 0.11 - nodes in this community are weakly interconnected._
- **Should `Meal Resolution & Order Generation` be split into smaller, more focused modules?**
  _Cohesion score 0.10317460317460317 - nodes in this community are weakly interconnected._
- **Should `Data Migration Pipeline` be split into smaller, more focused modules?**
  _Cohesion score 0.11711711711711711 - nodes in this community are weakly interconnected._