# Graph Report - Padea  (2026-06-02)

## Corpus Check
- 88 files · ~72,206 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1432 nodes · 2278 edges · 118 communities (94 shown, 24 thin omitted)
- Extraction: 81% EXTRACTED · 19% INFERRED · 0% AMBIGUOUS · INFERRED: 435 edges (avg confidence: 0.75)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `88e6263c`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Meal Resolution & Order Generation|Meal Resolution & Order Generation]]
- [[_COMMUNITY_Data Migration Pipeline|Data Migration Pipeline]]
- [[_COMMUNITY_Dietary Requirements Data|Dietary Requirements Data]]
- [[_COMMUNITY_Business Logic & System Overview|Business Logic & System Overview]]
- [[_COMMUNITY_Caterer Directory|Caterer Directory]]
- [[_COMMUNITY_Design Decisions & Rationale|Design Decisions & Rationale]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Order Email Dispatch|Order Email Dispatch]]
- [[_COMMUNITY_Schema Architecture|Schema Architecture]]
- [[_COMMUNITY_Absence Records|Absence Records]]
- [[_COMMUNITY_School Exclusion Records|School Exclusion Records]]
- [[_COMMUNITY_Claude Settings|Claude Settings]]
- [[_COMMUNITY_Session Date Parsing|Session Date Parsing]]
- [[_COMMUNITY_QR Code Instance|QR Code Instance]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
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
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 72|Community 72]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 76|Community 76]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 80|Community 80]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 85|Community 85]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 88|Community 88]]
- [[_COMMUNITY_Community 89|Community 89]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]

## God Nodes (most connected - your core abstractions)
1. `Record` - 72 edges
2. `MockDatabase` - 70 edges
3. `register_orders()` - 24 edges
4. `Tables (14)` - 17 edges
5. `Assignment` - 16 edges
6. `Webapp — Student Meal Form` - 16 edges
7. `generate_orders()` - 15 edges
8. `cacheGet()` - 14 edges
9. `cacheSet()` - 14 edges
10. `evaluate()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `atFetch()` --semantically_similar_to--> `airtable_get()`  [INFERRED] [semantically similar]
  webapp/app.js → scripts/support.py
- `atPost()` --semantically_similar_to--> `airtable_post()`  [INFERRED] [semantically similar]
  output/webapp/app.js → scripts/support.py
- `is_item_compatible()` --semantically_similar_to--> `isItemCompatible()`  [INFERRED] [semantically similar]
  scripts/generate_orders.py → output/webapp/app.js
- `QR Code → Session-Scoped Webapp URL Pattern` --conceptually_related_to--> `app`  [INFERRED]
  scripts/generate_qr.py → webapp/app.js
- `Upsert Pattern for Meal Selections (overwrite on re-scan)` --implements--> `Student Meal Web App SPA (index.html)`  [INFERRED]
  plans/implementation_plan.md → output/webapp/index.html

## Hyperedges (group relationships)
- **Full Migration Pipeline: PDF Cache → Parse (LLM/Heuristic) → Airtable Post** — scripts_cache_pdf_cache_pdf, scripts_support_ask_llm, scripts_support_airtable_post [INFERRED 0.85]
- **Order Generation Flow: Resolve Meals → Enforce Min Qty → Write to Airtable → Format Email** — scripts_generate_orders_resolve_student_meal, scripts_generate_orders_enforce_min_qty, scripts_generate_orders_write_orders_to_airtable, scripts_send_orders_format_email [INFERRED 0.85]
- **Student Interaction Loop: QR Scan → Webapp → Select Meal + Rate → Informs Next Order** — scripts_generate_qr_main, webapp_app_selectmeal, webapp_app_submitrating, scripts_generate_orders_resolve_student_meal [INFERRED 0.75]
- **Catering Pipeline: Student Selection → Order Engine → Caterer Email** — webapp_index_spa, plans_impl_plan_ai_gap_filling, concept_caterer_email_format [EXTRACTED 0.95]
- **Caterer Data Flow: PDF → Cache → Airtable** — resources_caterer_menus_pdf, cache_caterer_menus_lakehouse, converted_caterers_lakehouse [EXTRACTED 0.95]
- **Order Validation: Dietary + Min Qty + Fallback Logic** — plans_impl_plan_dietary_filtering, plans_impl_plan_min_qty_enforcement, plans_impl_revised_fallback_logic [INFERRED 0.85]

## Communities (118 total, 24 thin omitted)

### Community 1 - "Meal Resolution & Order Generation"
Cohesion: 0.09
Nodes (32): Dietary Compatibility Filter (Positive + Negative Requirements), 3-Step Meal Resolution: Explicit Selection → Previous Week → AI Assigned, ai_assign_meal(), build_lookups(), determine_round(), enforce_min_qty(), find_previous_selection(), generate_orders() (+24 more)

### Community 2 - "Data Migration Pipeline"
Cohesion: 0.06
Nodes (56): dietary_mappings.json — Dietary String Translation Cache, LLM-with-Heuristic-Fallback Pattern, Clear-Parse-Link-Post Migration Pattern, Two-Pass Schema Creation (Resolves Circular Links), absences.py — Absences Migration, caterer_contacts.py — Caterer Contacts Migration, _clean_school_names(), _extract_json_block() (+48 more)

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
Cohesion: 0.07
Nodes (30): bestVariantSeverity(), checkCompatibility(), clearKnownStudent(), clearOptedOutLock(), CONSTRAINT_PHRASE, el, getKnownStudent(), getSubmittedFlag() (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.33
Nodes (4): Seed the Dietary Restrictions table from `scripts/dietary_data.py`.  This MUST r, all_restriction_names(), Hard-coded dietary-restriction hierarchy.  Each restriction lists its *direct* S, Flat list of all restriction names, including those only referenced     as super

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

### Community 13 - "Session Date Parsing"
Cohesion: 0.60
Nodes (4): _clean_str(), _parse_date(), _parse_year_levels(), run()

### Community 14 - "QR Code Instance"
Cohesion: 1.00
Nodes (3): QR Code - Moreton Bay Boys' College (2026-05-02), Moreton Bay Boys' College, Tutoring Session - Moreton Bay Boys' College 2026-05-02

### Community 15 - "Community 15"
Cohesion: 0.53
Nodes (4): _parse_absences(), _parse_date(), _ParsedAbsence, run()

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
Cohesion: 0.13
Nodes (16): QR Code → Session-Scoped Webapp URL Pattern, apiKey(), app, atGetRecord(), atPatch(), atPost(), CACHE_TTL, DIETARY_OPTIONS (+8 more)

### Community 28 - "Community 28"
Cohesion: 0.33
Nodes (5): Phase 1: Schema + Order Engine, Phase 2: Student Web App, Phase 3: Email + QR, Phase 4: Verification, Tasks

### Community 29 - "Community 29"
Cohesion: 0.40
Nodes (3): Answer, Q: Why does airtable_get() connect Data Migration Pipeline to Order Email Dispatch, Meal Resolution & Order Generation, Student Webapp & QR System?, Source Nodes

### Community 34 - "Community 34"
Cohesion: 0.50
Nodes (3): 1st Iteration, 2nd Iteration, 3rd Iteration

### Community 35 - "Community 35"
Cohesion: 0.27
Nodes (8): all_restriction_names(), Hard-coded dietary-restriction hierarchy.  Each restriction lists its *direct* S, Flat list of all restriction names, including those only referenced     as super, run(), _clean_int(), _clean_str(), _resolve_school_name(), run()

### Community 37 - "Community 37"
Cohesion: 0.05
Nodes (45): format_parent_email(), format_student_email(), manage_url(), meals_url(), send_meals_links.py — Email parents or students a personalised meal-preference l, send_links(), SessionLink, format_email_body() (+37 more)

### Community 38 - "Community 38"
Cohesion: 0.06
Nodes (60): ALL_VIEWS, allRestrictions, apiFetch(), backToSessions(), bestVariantSeverity(), buildHierarchyMaps(), buildVariantMap(), _cache (+52 more)

### Community 39 - "Community 39"
Cohesion: 0.07
Nodes (38): api_approve_proposal(), api_get_caterer(), api_get_caterer_menu(), api_get_dietary_restrictions(), api_get_feedback(), api_get_proposal(), api_get_session(), api_get_session_students() (+30 more)

### Community 40 - "Community 40"
Cohesion: 0.06
Nodes (36): Exception, Absences(), base(), CatererFeedback(), Caterers(), CatererSwitchProposals(), Database, DietaryRestrictions() (+28 more)

### Community 41 - "Community 41"
Cohesion: 0.10
Nodes (31): A read-only Airtable record envelope with typed ``fields``.      Construct via :, Record, caterer_a(), caterer_b(), caterer_meat_only(), dietary_records(), make_students(), manager_alpha() (+23 more)

### Community 42 - "Community 42"
Cohesion: 0.11
Nodes (12): dispatch(), Invoke *func* with kwargs built from URL groups, payload, and db.      Named cap, local_ip(), main(), PadeaHandler, host_webapp.py — Serve the Padea webapp over the local network.  Binds to 0.0.0., Best-guess LAN IP by connecting a UDP socket (never actually sends)., Serves static webapp files and handles /api/proposal/* routes. (+4 more)

### Community 43 - "Community 43"
Cohesion: 0.08
Nodes (25): 1. Picker — "Who are you?", 2. Form, 3. Meal picker, 4. Done, 5. Locked, API endpoints, Brand, Caching strategy (+17 more)

### Community 44 - "Community 44"
Cohesion: 0.14
Nodes (14): build(), _CatererBatch, clear_existing_orders(), get_next_week_dates(), get_week_label(), load(), _print_summary(), register_orders.py — Snapshot student meal preferences into the Orders table.  F (+6 more)

### Community 45 - "Community 45"
Cohesion: 0.15
Nodes (11): execute(), execute_caterer_switch.py — Execute a caterer switch proposal.  Reads the named, Mark a Caterer Switch Proposal as Rejected with optional coordinator notes., Resolved view of an approved Caterer Switch Proposal., reject(), _resolve_context(), SwitchContext, _approved_proposal() (+3 more)

### Community 46 - "Community 46"
Cohesion: 0.09
Nodes (21): Caterer management, code:bash (# .env at project root (not committed):), code:bash (# Post-order constraints (min-qty + session totals)), code:bash (./run migrate schema         # idempotent — diffs schema.py ), code:bash (./run migrate                # full clean-slate import (all ), code:bash (# PDF extraction (run if a resources/*.pdf changes)), code:bash (./run orders                       # generate then queue ema), code:bash (# Generate QR code PNGs (one per session) in output/qrcodes/) (+13 more)

### Community 47 - "Community 47"
Cohesion: 0.10
Nodes (20): Absences, Caterer Feedback, Caterer Switch Proposals, Caterers, code:block1 (Schools ──< Sessions >── Caterers ──< Menu Items >── Dietary), Data Model, Dietary Restrictions, Exclusions (+12 more)

### Community 48 - "Community 48"
Cohesion: 0.10
Nodes (20): Algorithm, Behaviour, code:block1 (1. Flip any pending caterer switches: for every Session with), code:block2 (Hi <First name>,), code:bash (python scripts/tests/order_constraints.py), Constraint verification, Email format, Explicit preference override (+12 more)

### Community 49 - "Community 49"
Cohesion: 0.19
Nodes (16): build(), create_proposal_and_email(), evaluate(), force_proposal(), format_no_candidate_email(), format_proposal_email(), format_watch_email(), get_effective_week() (+8 more)

### Community 50 - "Community 50"
Cohesion: 0.19
Nodes (10): caterer_covers_all_students(), Return ``(True, None)`` if every non-opted-out student at the school has     at, ``score = 0.6 * avg_at_this_school + 0.4 * avg_overall`` (or just     overall wh, score_candidate(), _make_eval_index(), Tests for scripts/actions/evaluate_caterers.py.  Covers: get_rolling_stats (wind, Feedback index is keyed by (session_id, caterer_id); the school-scoped     avera, Minimal namespace sufficient for the pure evaluation functions. (+2 more)

### Community 51 - "Community 51"
Cohesion: 0.19
Nodes (18): BaseModel, Absence, Caterer, CatererFeedback, CatererSwitchProposal, Config, DietaryRestriction, Exclusion (+10 more)

### Community 52 - "Community 52"
Cohesion: 0.22
Nodes (7): has_active_proposal(), True if a Pending / Approved / Executed proposal already exists., True if a Rejected proposal for this pair exists since ``term_start``., was_rejected_this_term(), _proposal(), TestHasActiveProposal, TestWasRejectedThisTerm

### Community 53 - "Community 53"
Cohesion: 0.12
Nodes (16): A "next term" reset workflow, Actually sending email, Calendar export, Caterer email format A/B with the coordinator, Idempotency for outbound emails, Live hosting for the webapp, Multi-meal orders, Planned but unbuilt (+8 more)

### Community 54 - "Community 54"
Cohesion: 0.12
Nodes (16): Action Script Tests, Adding tests, code:bash (# Run the full suite), code:bash (PYTHONPATH=$PWD:$PWD/scripts python scripts/tests/run_all.py), code:block3 (scripts/tests/), `evaluate_caterers.py`, `execute_caterer_switch.py`, File layout (+8 more)

### Community 55 - "Community 55"
Cohesion: 0.12
Nodes (15): _comment, negative_keywords, Dairy Free, Halal, Kosher, No Beef, No Fish, No Lamb (+7 more)

### Community 56 - "Community 56"
Cohesion: 0.33
Nodes (16): apiFetch(), atGet(), atList(), cacheGet(), cacheSet(), loadCaterer(), loadDietaryRestrictions(), loadExistingFeedback() (+8 more)

### Community 57 - "Community 57"
Cohesion: 0.29
Nodes (6): api_get_manager_sessions(), api_update_dietary_requirements(), MockDatabase, In-memory replacement for support.database.Database.      Instantiate once per t, TestApiGetManagerSessions, TestApiUpdateDietaryRequirements

### Community 58 - "Community 58"
Cohesion: 0.25
Nodes (8): is_student_excluded(), OrderingData, Check if a student is excluded from this session on this specific date.      ``s, Raw records loaded once from Airtable for the order build., _make_data(), _make_index(), Tests for scripts/actions/register_orders.py.  Covers: is_student_excluded, assi, TestIsStudentExcluded

### Community 59 - "Community 59"
Cohesion: 0.17
Nodes (3): MockTable, MockTable and MockDatabase for testing Padea action scripts without connecting t, In-memory replacement for support.database.Table.      ``all()`` ignores the for

### Community 60 - "Community 60"
Cohesion: 0.14
Nodes (13): Allergy-grade restrictions, code:block1 (Vegan), Compatibility check (order generator), Compatibility check (webapp implementation), Dietary System, Edge cases worth knowing, Explicit override and hard block, Halal-by-default (+5 more)

### Community 61 - "Community 61"
Cohesion: 0.33
Nodes (4): api_override_order(), _order(), Tests for the manage-page API endpoints added to scripts/actions/api.py.  Covers, TestApiOverrideOrder

### Community 62 - "Community 62"
Cohesion: 0.27
Nodes (8): _build_feedback_index(), FeedbackEntry, get_rolling_stats(), Group feedback by (session_id, caterer_id), sorted by date ascending., Return rolling-window statistics for the most recent ROLLING_WINDOW     distinct, RollingStats, _fb(), TestGetRollingStats

### Community 63 - "Community 63"
Cohesion: 0.27
Nodes (8): EvaluationData, find_candidates(), Return sorted ``(score, caterer_id, caterer_name)`` for eligible     replacement, Raw records loaded from Airtable for the evaluation pass., _build_eval_index(), Build a real EvaluationIndex from minimal test data., Verify find_candidates applies the dietary hard filter end-to-end,     not just, TestFindCandidates

### Community 64 - "Community 64"
Cohesion: 0.17
Nodes (11): Sheet: CHAC - Monday, Sheet: CHAC - Wednesday, Sheet: ISHS - Monday, Sheet: ISHS - Thursday, Sheet: ISHS - Tuesday, Sheet: JPC - Tuesday, Sheet: JPC - Wednesday, Sheet: LC - Monday (+3 more)

### Community 65 - "Community 65"
Cohesion: 0.17
Nodes (11): Absences, Caterers, Edge Cases, Email pipeline, Exclusions, Operational, Order generation, Sessions (+3 more)

### Community 66 - "Community 66"
Cohesion: 0.20
Nodes (8): populate_mock_db(), Regression testing suite for catchable edge cases and automated self-healing.  A, Populate a MockDatabase using the serialized 'state_snapshot' dictionary from a, Base regression test suite demonstrating automated self-healing replication., Utility to load a failure JSON snapshot relative to the project root., Concrete example: replicates a validation failure, mock-loads it, and shows regr, Concrete example: replicates an unhandled logical exception in ordering logic., TestSelfHealingRegression

### Community 67 - "Community 67"
Cohesion: 0.38
Nodes (5): Assignment, enforce_min_qty(), Enforce caterer per-item min-qty by dissolving under-populated items.      For e, One student's (session, item) tuple ready to write to Orders., TestEnforceMinQty

### Community 68 - "Community 68"
Cohesion: 0.25
Nodes (5): compute_max_variety(), _find_min_qty(), Return the most distinct items we can order while still satisfying the     cater, Return the per-item minimum quantity for the given number of distinct     items,, TestComputeMaxVariety

### Community 69 - "Community 69"
Cohesion: 0.18
Nodes (11): applyOptedOutLock(), hasOptedOut(), isInTransition(), loadFormData(), loadPickerData(), menuCatererId(), refreshFormFromState(), renderStudentList() (+3 more)

### Community 70 - "Community 70"
Cohesion: 0.36
Nodes (5): api_get_session_students_all(), All students in a session with no Last-Submitted filter — used by the manager pa, Monday session pre-populated with the given student IDs in its Students field., _session_with_students(), TestApiGetSessionStudentsAll

### Community 71 - "Community 71"
Cohesion: 0.24
Nodes (5): assign_variety_meal(), Pick the least-ordered compatible meal to spread variety across the     batch. U, Minimal namespace that satisfies assign_*meal — only dietary_hierarchy., _simple_index(), TestAssignVarietyMeal

### Community 72 - "Community 72"
Cohesion: 0.24
Nodes (9): has_opted_out(), is_item_compatible(), item_incompatibility_ids(), Shared dietary-compatibility logic.  Used by:   - scripts/actions/register_order, Convert dietary record IDs to their restriction-name strings., True if any of the student's dietary IDs is the 'Opted out of Catering' tag., Check that a menu item can be assigned to a student with the given     Dietary R, Return the restriction IDs the item *definitely* violates for this     student ( (+1 more)

### Community 74 - "Community 74"
Cohesion: 0.31
Nodes (5): assign_fallback_meal(), OrderingIndex, Pre-computed lookups derived from :class:`OrderingData`., Pick the best compatible meal weighted by:       - Current batch popularity (80%, TestAssignFallbackMeal

### Community 75 - "Community 75"
Cohesion: 0.33
Nodes (8): check_min_qty(), check_session_totals(), ConstraintsData, expected_eating_count(), load(), main(), order_constraints.py — Verify that registered Orders for next week:   1. Satisfy, Count enrolled students at this session who are not absent, excluded, or opted o

### Community 76 - "Community 76"
Cohesion: 0.36
Nodes (3): load_substitutions(), Return a (session_record_id, date) → substitute_manager_record_id mapping., TestLoadSubstitutions

### Community 77 - "Community 77"
Cohesion: 0.39
Nodes (3): flip_incoming_caterers(), Commit any pending caterer switches before this week's order is built.      If a, TestFlipIncomingCaterers

### Community 78 - "Community 78"
Cohesion: 0.25
Nodes (7): Business Context, The bottleneck this project fixes, The caterers, The on-site managers, The roster of schools, What "fixed" looks like, What Padea does

### Community 79 - "Community 79"
Cohesion: 0.25
Nodes (7): code:block1 (dietary_restrictions       # (no deps) — full restriction hi), LLM-extracted fields, Migration order (load-bearing), Migration Pipeline, Re-running migrations, Source files, Verification

### Community 80 - "Community 80"
Cohesion: 0.43
Nodes (3): get_term_start(), Return the start date of the current QLD school term., TestGetTermStart

### Community 81 - "Community 81"
Cohesion: 0.29
Nodes (6): At a glance, code:block1 (Tuesday session     →   QR code → mobile webapp), code:block2 (.), Padea Catering Automation — Project Overview, Repository layout, Tech stack

### Community 82 - "Community 82"
Cohesion: 0.33
Nodes (6): EvaluationIndex, Pre-computed lookups derived from :class:`EvaluationData`., build_hierarchy(), DietaryHierarchy, Pre-computed lookup tables built from the Dietary Restrictions table.      A res, Build a :class:`DietaryHierarchy` from a list of restriction records.

### Community 83 - "Community 83"
Cohesion: 0.33
Nodes (4): graphify, Python scripting, Self-Healing & Agent-Ready Architecture Standards, What this project does

### Community 84 - "Community 84"
Cohesion: 0.33
Nodes (5): code:javascript (localStorage.setItem('padea_submitted_' + sessionId, 'true')), Context, Problem Description, Problem: Shared Dropdown Without Auth allows Student Pranks, Proposed Solution (AI Actionable)

### Community 85 - "Community 85"
Cohesion: 0.33
Nodes (5): 30 — `EmailStatus` literal advertises `Send Immediately` but the schema doesn't, code:python (EmailStatus = Literal["Queued", "Send Immediately", "Sent", ), code:python (fields["Status"] = "Send Immediately" if immediate else "Que), code:python ("options": {), Fix

### Community 86 - "Community 86"
Cohesion: 0.40
Nodes (6): atCreate(), atFetch(), atUpdate(), cacheBust(), makeId(), persistChanges()

### Community 87 - "Community 87"
Cohesion: 0.60
Nodes (4): generate_qr(), main(), make_session_url(), generate_qr.py — Generate QR code PNGs for each session's web app URL.  Each QR

### Community 88 - "Community 88"
Cohesion: 0.40
Nodes (3): 29 — Outbound email queueing is not idempotent, code:python (existing = db.ScheduledEmails.all(formula=f"{{Email ID}}='{e), Fix

### Community 89 - "Community 89"
Cohesion: 0.40
Nodes (4): 31 — `send_orders.py` processes every Weekly Order with `Week Start >= TODAY()`, code:python (def load_pending_orders(db: Database) -> list[Record[WeeklyO), code:python (next_monday = get_next_week_dates()["Monday"].isoformat()), Fix

### Community 90 - "Community 90"
Cohesion: 0.40
Nodes (4): Context, Problem Description, Problem: Explicit Override of Medical Allergies is a Liability, Proposed Solution (AI Actionable)

### Community 91 - "Community 91"
Cohesion: 0.40
Nodes (4): Context, Problem Description, Problem: Swapped Meals Cause Classroom Confusion and Waste, Proposed Solution (AI Actionable)

### Community 92 - "Community 92"
Cohesion: 0.50
Nodes (3): 21 — Caterer feedback loaded by `register_orders.py` but never used, code:python (@dataclass(frozen=True)), Fix

### Community 93 - "Community 93"
Cohesion: 0.50
Nodes (3): 11 — Airtable API key exposed in the webapp bundle ✓ RESOLVED, code:js (const CONFIG = {), Fix applied

### Community 95 - "Community 95"
Cohesion: 0.50
Nodes (3): 24 — `host_webapp.py` uses `os.chdir`, code:python (def main(port=DEFAULT_PORT):), Fix

### Community 96 - "Community 96"
Cohesion: 0.50
Nodes (3): 28 — `MIN_SESSIONS = 0` disables the caterer-switch sanity floor, code:python (SWITCH_THRESHOLD = 2.5), Fix

### Community 97 - "Community 97"
Cohesion: 0.50
Nodes (3): 32 — `host_webapp.py` startup hints point at the old `./run qr` command, code:python ("""), Fix

## Knowledge Gaps
- **359 isolated node(s):** `TAG_SHORT`, `CONSTRAINT_PHRASE`, `_memCache`, `views`, `el` (+354 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `_parse_menus_heuristic()` connect `Data Migration Pipeline` to `Community 39`?**
  _High betweenness centrality (0.109) - this node is a cross-community bridge._
- **Why does `Record` connect `Community 41` to `Community 37`, `Community 39`, `Community 40`, `Community 44`, `Community 45`, `Community 50`, `Community 52`, `Community 57`, `Community 58`, `Community 59`, `Community 61`, `Community 63`, `Community 66`, `Community 67`, `Community 70`, `Community 71`, `Community 72`, `Community 74`, `Community 76`, `Community 77`, `Community 82`?**
  _High betweenness centrality (0.105) - this node is a cross-community bridge._
- **Are the 67 inferred relationships involving `Record` (e.g. with `DietaryHierarchy` and `.create()`) actually correct?**
  _`Record` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 67 inferred relationships involving `MockDatabase` (e.g. with `TestExecuteCatererSwitch` and `TestApiGetManagerSessions`) actually correct?**
  _`MockDatabase` has 67 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `register_orders()` (e.g. with `has_opted_out()` and `is_item_compatible()`) actually correct?**
  _`register_orders()` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `Assignment` (e.g. with `DietaryHierarchy` and `TestIsStudentExcluded`) actually correct?**
  _`Assignment` has 12 INFERRED edges - model-reasoned connections that need verification._
- **What connects `TAG_SHORT`, `CONSTRAINT_PHRASE`, `_memCache` to the rest of the system?**
  _517 weakly-connected nodes found - possible documentation gaps or missing edges._