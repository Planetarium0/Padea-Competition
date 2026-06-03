# Graph Report - .  (2026-06-03)

## Corpus Check
- 106 files · ~75,747 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 952 nodes · 1782 edges · 81 communities (60 shown, 21 thin omitted)
- Extraction: 74% EXTRACTED · 26% INFERRED · 0% AMBIGUOUS · INFERRED: 455 edges (avg confidence: 0.72)
- Token cost: 2,800 input · 1,950 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Order Registration Pipeline|Order Registration Pipeline]]
- [[_COMMUNITY_Webapp Meal Selection|Webapp Meal Selection]]
- [[_COMMUNITY_Migration & Notification|Migration & Notification]]
- [[_COMMUNITY_Order Email Generation|Order Email Generation]]
- [[_COMMUNITY_Session & Caterer Data|Session & Caterer Data]]
- [[_COMMUNITY_Self-Healing Error Infrastructure|Self-Healing Error Infrastructure]]
- [[_COMMUNITY_Schema & Resolved Issues|Schema & Resolved Issues]]
- [[_COMMUNITY_Pydantic Data Schemas|Pydantic Data Schemas]]
- [[_COMMUNITY_Manage Page UI|Manage Page UI]]
- [[_COMMUNITY_Caterer Switch Execution|Caterer Switch Execution]]
- [[_COMMUNITY_Caterer Evaluation Engine|Caterer Evaluation Engine]]
- [[_COMMUNITY_Caterer Proposal Lifecycle|Caterer Proposal Lifecycle]]
- [[_COMMUNITY_Caterer Scoring & Filtering|Caterer Scoring & Filtering]]
- [[_COMMUNITY_Database Access Layer|Database Access Layer]]
- [[_COMMUNITY_Meal Assignment Logic|Meal Assignment Logic]]
- [[_COMMUNITY_Claude Agent Harness|Claude Agent Harness]]
- [[_COMMUNITY_Database Utilities|Database Utilities]]
- [[_COMMUNITY_Dietary Negative Keywords|Dietary Negative Keywords]]
- [[_COMMUNITY_Idempotent Order Registration|Idempotent Order Registration]]
- [[_COMMUNITY_Webapp Dietary Keywords|Webapp Dietary Keywords]]
- [[_COMMUNITY_Manager ID Resolution|Manager ID Resolution]]
- [[_COMMUNITY_Student Exclusion Check|Student Exclusion Check]]
- [[_COMMUNITY_Scheduling & Cron Targets|Scheduling & Cron Targets]]
- [[_COMMUNITY_Database Table Tests|Database Table Tests]]
- [[_COMMUNITY_Switch Proposal UI|Switch Proposal UI]]
- [[_COMMUNITY_Candidate Discovery|Candidate Discovery]]
- [[_COMMUNITY_Feedback & Rolling Stats|Feedback & Rolling Stats]]
- [[_COMMUNITY_Order Batch Building|Order Batch Building]]
- [[_COMMUNITY_Minimum Quantity Enforcement|Minimum Quantity Enforcement]]
- [[_COMMUNITY_Order Constraints & Models|Order Constraints & Models]]
- [[_COMMUNITY_Pydantic Schema Tests|Pydantic Schema Tests]]
- [[_COMMUNITY_Variety Optimization|Variety Optimization]]
- [[_COMMUNITY_Webapp Architecture Docs|Webapp Architecture Docs]]
- [[_COMMUNITY_Order Timing & Constraints|Order Timing & Constraints]]
- [[_COMMUNITY_Dietary Hierarchy Build|Dietary Hierarchy Build]]
- [[_COMMUNITY_QR Email Generation|QR Email Generation]]
- [[_COMMUNITY_Manage UI Navigation|Manage UI Navigation]]
- [[_COMMUNITY_Dietary UI Compatibility|Dietary UI Compatibility]]
- [[_COMMUNITY_Manager Override Flow|Manager Override Flow]]
- [[_COMMUNITY_Meal Link Emails|Meal Link Emails]]
- [[_COMMUNITY_Caterer Data Models|Caterer Data Models]]
- [[_COMMUNITY_Database Test Infrastructure|Database Test Infrastructure]]
- [[_COMMUNITY_Keyword Fallback System|Keyword Fallback System]]
- [[_COMMUNITY_Webapp Variant Cache|Webapp Variant Cache]]
- [[_COMMUNITY_Term Boundary Logic|Term Boundary Logic]]
- [[_COMMUNITY_Project Overview & Goals|Project Overview & Goals]]
- [[_COMMUNITY_Error Handling Module|Error Handling Module]]
- [[_COMMUNITY_Allergy & Constraint Rules|Allergy & Constraint Rules]]
- [[_COMMUNITY_Junction Field Tests|Junction Field Tests]]
- [[_COMMUNITY_Meal Selection Modal|Meal Selection Modal]]
- [[_COMMUNITY_Edge Cases Docs|Edge Cases Docs]]
- [[_COMMUNITY_Compatibility Records|Compatibility Records]]
- [[_COMMUNITY_QR Code Generation|QR Code Generation]]
- [[_COMMUNITY_Student Data Migration|Student Data Migration]]
- [[_COMMUNITY_User Interaction Utilities|User Interaction Utilities]]
- [[_COMMUNITY_Sandbox Safety Guards|Sandbox Safety Guards]]
- [[_COMMUNITY_Order Data Structures|Order Data Structures]]
- [[_COMMUNITY_Database Reset|Database Reset]]
- [[_COMMUNITY_Digital Ticket & Override|Digital Ticket & Override]]
- [[_COMMUNITY_LLM & Logging Utils|LLM & Logging Utils]]
- [[_COMMUNITY_Airtable Query Memory|Airtable Query Memory]]
- [[_COMMUNITY_Caterer Contacts PDF|Caterer Contacts PDF]]
- [[_COMMUNITY_Caterer Menus PDF|Caterer Menus PDF]]
- [[_COMMUNITY_Exclusions PDF|Exclusions PDF]]
- [[_COMMUNITY_Absences PDF|Absences PDF]]
- [[_COMMUNITY_Webapp Index|Webapp Index]]
- [[_COMMUNITY_Variety Threshold|Variety Threshold]]
- [[_COMMUNITY_Switch Threshold|Switch Threshold]]
- [[_COMMUNITY_Rolling Window|Rolling Window]]
- [[_COMMUNITY_Proposal Status|Proposal Status]]
- [[_COMMUNITY_Verbose Log|Verbose Log]]
- [[_COMMUNITY_All Restriction Names|All Restriction Names]]
- [[_COMMUNITY_Business Context|Business Context]]
- [[_COMMUNITY_Diet Docs|Diet Docs]]
- [[_COMMUNITY_Chdir Fix|Chdir Fix]]
- [[_COMMUNITY_Duplicate Reviews|Duplicate Reviews]]
- [[_COMMUNITY_Vegetarian Option|Vegetarian Option]]

## God Nodes (most connected - your core abstractions)
1. `Record` - 63 edges
2. `MockDatabase` - 49 edges
3. `Table` - 35 edges
4. `register_orders()` - 28 edges
5. `Database` - 22 edges
6. `TestPydanticSchemas` - 19 edges
7. `evaluate()` - 17 edges
8. `_Base` - 17 edges
9. `Assignment` - 16 edges
10. `load_substitutions()` - 15 edges

## Surprising Connections (you probably didn't know these)
- `OOP Refactor Instruction` --rationale_for--> `Database`  [INFERRED]
  .old/resolved/refactor.md → scripts/support/database.py
- `DIETARY_HIERARCHY Data Constant` --semantically_similar_to--> `DietaryHierarchy`  [INFERRED] [semantically similar]
  data/dietary_data.py → scripts/support/compatibility.py
- `TABLES_SCHEMA Airtable Schema Definition` --semantically_similar_to--> `Initial Supabase Schema Migration SQL`  [INFERRED] [semantically similar]
  data/schema.py → supabase/migrations/20260602230008_initial_schema.sql
- `send_meals_links.send_links — Email Meal Preference Links` --references--> `meals.html — Student Meal Rating & Preference Page`  [INFERRED]
  scripts/actions/send_meals_links.py → webapp/meals.html
- `send_meals_links.send_links — Email Meal Preference Links` --references--> `manage.html — Student Management Page`  [INFERRED]
  scripts/actions/send_meals_links.py → webapp/manage.html

## Hyperedges (group relationships)
- **Dietary Compatibility System — Hierarchy Maps + Keyword Fallback + Legend Tags** — webapp_app_buildhierarchymaps, webapp_app_checkcompatibility, data_dietary_keywords, concept_caterer_legend_tags, concept_negative_keyword_fallback [EXTRACTED 0.95]
- **Migration Pipeline — All Migration Modules Orchestrated in Order** — migrations_migrate_run, migrations_dietary_restrictions_run, migrations_schools_run, migrations_caterers_run, migrations_caterer_contacts_run, migrations_caterer_menus_run, migrations_sessions_run, migrations_students_run, migrations_absences_run, migrations_exclusions_run [EXTRACTED 1.00]
- **Webapp Pages — All Share Supabase Client for Data Access** — webapp_app_appinit, webapp_manage_init, webapp_switch_proposal_page, webapp_supabase_client [EXTRACTED 0.95]
- **Caterer Switch Pipeline: Evaluate → Execute → Flip** — actions_evaluate_caterers_evaluate, actions_execute_caterer_switch_execute, actions_register_orders_flip_incoming_caterers [INFERRED 0.85]
- **Order Registration Pipeline: Data → Index → Assign → Enforce → Write** — actions_register_orders_orderingdata, actions_register_orders_orderingindex, actions_register_orders_register_orders [EXTRACTED 1.00]
- **Self-Healing Infrastructure: Handler → Failure JSON → Regression Test** — support_error_handler_self_healing_error_handler, tests_test_edge_cases_testselfhealingregression, tests_test_edge_cases_populate_mock_db [INFERRED 0.85]
- **Dietary Compatibility Check Pipeline** — support_compatibility_buildhierarchy, support_compatibility_isitemcompatible, data_dietary_keywords_negativekeywords [EXTRACTED 0.95]
- **Typed Database Access Layer** — support_database_database, support_database_table, support_database_record [EXTRACTED 0.95]
- **Self-Healing Claude Sandbox Execution Flow** — support_run_claude_agent_claudeharness, support_run_claude_agent_pathisolation, support_run_claude_agent_gitguard [EXTRACTED 0.95]
- **End-to-End Ordering Pipeline: register_orders → send_orders → Scheduled Emails → Airtable Automation** — current_05_ordering_pipeline_registerorders, current_05_ordering_pipeline_sendorders, current_02_data_model_scheduledemails [EXTRACTED 1.00]
- **Shared Dietary Compatibility: Taxonomy + is_item_compatible + dietary_keywords.json used by both webapp and order generator** — current_06_dietary_system_dietarytaxonomy, current_06_dietary_system_compatibilitycheck, current_04_webapp_webapp [EXTRACTED 1.00]
- **Prank Prevention System: One-Way Lockout + Server-Side Roster Filter + Last Submitted Field** — current_04_webapp_onewaylockout, current_02_data_model_students, old_resolved_26_no_auth_student_picker_pranks_onewayroster [INFERRED 0.85]
- **Session Identity: Sessions Data, Caterer Assignment, and QR Ticket Generation** — converted_sessions_sessions_sheet, converted_caterers_caterers_sheet, concept_session_qr_digital_ticket [INFERRED 0.85]
- **Indooroopilly State High School: Multi-day Sessions, Kenko Sushi House, QR Codes** — converted_caterers_kenko_sushi_house, converted_sessions_indooroopilly_state_high_school_monday, converted_sessions_indooroopilly_state_high_school_tuesday, converted_sessions_indooroopilly_state_high_school_thursday, qrcodes_indooroopilly_state_high_school_monday_qrcode, qrcodes_indooroopilly_state_high_school_tuesday_qrcode, qrcodes_indooroopilly_state_high_school_thursday_qrcode [INFERRED 0.85]
- **Guzman y Gomez: Loreto and Cannon Hill Sessions in Central Brisbane** — converted_caterers_guzman_y_gomez, converted_sessions_loreto_college_monday, converted_sessions_loreto_college_tuesday, converted_sessions_cannon_hill_anglican_college_monday, converted_sessions_cannon_hill_anglican_college_wednesday [EXTRACTED 0.95]

## Communities (81 total, 21 thin omitted)

### Community 0 - "Order Registration Pipeline"
Cohesion: 0.05
Nodes (42): flip_incoming_caterers(), Commit any pending caterer switches before this week's order is built.      If a, load_substitutions(), A read-only database record envelope with typed ``fields``., Return a (session_id, date) → substitute_manager_id mapping.      Queries manage, Record, caterer_a(), caterer_b() (+34 more)

### Community 1 - "Webapp Meal Selection"
Cohesion: 0.06
Nodes (58): Caterer Switch Transition — Incoming Caterer Menu During Switch, Device Lockout — One Submission Per Device Per Day, Dietary Hierarchy Closure — Subset/Superset Closure Concept, app, app.init — Webapp Bootstrap, applyOptedOutLock(), buildHierarchyMaps(), cacheBust() (+50 more)

### Community 2 - "Migration & Notification"
Cohesion: 0.06
Nodes (47): send_meals_links.send_links — Email Meal Preference Links, LLM-then-Heuristic Fallback — LLM Parse with Local Fallback Pattern, Migration Pipeline — Ordered Data Migration Dependency Chain, all_restriction_names(), Hard-coded dietary-restriction hierarchy.  Each restriction lists its *direct* S, Flat list of all restriction names, including those only referenced     as super, _parse_absences(), _parse_date() (+39 more)

### Community 3 - "Order Email Generation"
Cohesion: 0.08
Nodes (27): format_email_body(), LineItem, load_order_details(), load_pending_orders(), process_orders(), send_orders.py — Format and send caterer order emails for next week.  Reads all, Aggregate individual Orders records for a Weekly Order into line items., Return a Markdown email body using only Airtable-supported formatting. (+19 more)

### Community 4 - "Session & Caterer Data"
Cohesion: 0.12
Nodes (30): Session QR Code Digital Ticket System, Caterers Data Sheet, Caterer: Guzman y Gomez, Caterer: Kenko Sushi House, Caterer: Lakehouse Victoria Point, Minimum Order Quantity by Menu Item Count, Caterer: Terrific Noodles, Session: Cannon Hill Anglican College - Monday (+22 more)

### Community 5 - "Self-Healing Error Infrastructure"
Cohesion: 0.09
Nodes (16): Self-Healing Failure Capture Pattern, Coerce complex objects (like Dataclasses, Sets, custom Records) to JSON-serializ, Context manager to catch, serialize, and prompt-heal failures in active workflow, self_healing_error_handler, UnhandledEdgeCaseError Exception, support Package __init__, Test runner for all Padea action-script unit tests.  Usage (from the project roo, suite() (+8 more)

### Community 6 - "Schema & Resolved Issues"
Cohesion: 0.09
Nodes (24): TABLES_SCHEMA Airtable Schema Definition, Problem 11: API Key Exposed in Webapp, Problem 28: MIN_SESSIONS Zero Bug, Problem 30: Send Immediately Email Status, OOP Refactor Instruction, approve_caterer_switch RPC Function, Initial Supabase Schema Migration SQL, Database (+16 more)

### Community 7 - "Pydantic Data Schemas"
Cohesion: 0.17
Nodes (21): BaseModel, Absence, _Base, Caterer, CatererFeedback, CatererSwitchProposal, DietaryRestriction, Exclusion (+13 more)

### Community 8 - "Manage Page UI"
Cohesion: 0.08
Nodes (18): ALL_VIEWS, allRestrictions, _cache, checkedDietIds, CONSTRAINT_PHRASE, DIET_DISPLAY_ORDER, filteredStudents, initialDietIds (+10 more)

### Community 9 - "Caterer Switch Execution"
Cohesion: 0.15
Nodes (11): execute(), execute_caterer_switch.py — Execute a caterer switch proposal.  Reads the named, Mark a Caterer Switch Proposal as Rejected with optional coordinator notes., Resolved view of an approved Caterer Switch Proposal., reject(), _resolve_context(), SwitchContext, _approved_proposal() (+3 more)

### Community 10 - "Caterer Evaluation Engine"
Cohesion: 0.16
Nodes (19): build(), create_proposal_and_email(), evaluate(), EvaluationIndex, force_proposal(), format_no_candidate_email(), format_proposal_email(), format_watch_email() (+11 more)

### Community 11 - "Caterer Proposal Lifecycle"
Cohesion: 0.20
Nodes (8): has_active_proposal(), True if a Pending / Approved / Executed proposal already exists., True if a Rejected proposal for this pair exists since ``term_start``., was_rejected_this_term(), _proposal(), Tests for scripts/actions/evaluate_caterers.py.  Covers: get_rolling_stats (wind, TestHasActiveProposal, TestWasRejectedThisTerm

### Community 12 - "Caterer Scoring & Filtering"
Cohesion: 0.18
Nodes (11): caterer_covers_all_students(), Return ``(True, None)`` if every non-opted-out student at the school has     at, ``score = 0.6 * avg_at_this_school + 0.4 * avg_overall`` (or just     overall wh, score_candidate(), Dietary Hard Filter for Caterer Candidates, _make_eval_index(), Feedback index is keyed by (session_id, caterer_id); the school-scoped     avera, Minimal namespace sufficient for the pure evaluation functions. (+3 more)

### Community 13 - "Database Access Layer"
Cohesion: 0.19
Nodes (16): Absences(), CatererFeedback(), Caterers(), CatererSwitchProposals(), DietaryRestrictions(), Exclusions(), ManagerSubstitutions(), MenuItems() (+8 more)

### Community 14 - "Meal Assignment Logic"
Cohesion: 0.15
Nodes (10): assign_fallback_meal(), assign_variety_meal(), Pick the best compatible meal weighted by:       - Current batch popularity (80%, Pick the least-ordered compatible meal to spread variety across the     batch. U, is_item_compatible(), Check that a menu item can be assigned to a student with the given     Dietary R, Minimal namespace that satisfies assign_*meal — only dietary_hierarchy., _simple_index() (+2 more)

### Community 15 - "Claude Agent Harness"
Cohesion: 0.17
Nodes (17): get_git_modified_files(), get_latest_error_prompt(), is_file_allowed(), main(), orchestrate_self_healing(), Invokes Claude Code in the restricted environment., Runs the post-execution test suite., Finds the most recent patch_prompt_*.md in cache/failures/ and returns its conte (+9 more)

### Community 16 - "Database Utilities"
Cohesion: 0.19
Nodes (7): from_env(), from_row(), Junction Map Configuration, Typed wrapper around a single Supabase table/view pair., Pop view-only junction fields from fields dict; return them separately., Table, View Map Configuration

### Community 17 - "Dietary Negative Keywords"
Cohesion: 0.12
Nodes (15): _comment, negative_keywords, Dairy Free, Halal, Kosher, No Beef, No Fish, No Lamb (+7 more)

### Community 18 - "Idempotent Order Registration"
Cohesion: 0.24
Nodes (9): clear_existing_orders(), Delete any existing Orders and draft Weekly Orders for next week., register_orders(), Idempotent Order Registration, has_opted_out(), Convert dietary record IDs to their restriction-name strings., True if any of the student's dietary IDs is the 'Opted out of Catering' tag., resolve_dietary_names() (+1 more)

### Community 19 - "Webapp Dietary Keywords"
Cohesion: 0.12
Nodes (15): _comment, negative_keywords, Dairy Free, Halal, Kosher, No Beef, No Fish, No Lamb (+7 more)

### Community 20 - "Manager ID Resolution"
Cohesion: 0.26
Nodes (4): Return the effective on-site manager ID and whether it is a substitute.      Che, resolve_manager_id(), TestResolveManagerId, TestResolveManagerId

### Community 21 - "Student Exclusion Check"
Cohesion: 0.26
Nodes (7): is_student_excluded(), Check if a student is excluded from this session on this specific date.      ``s, _make_data(), _make_index(), Tests for scripts/actions/register_orders.py.  Covers: is_student_excluded, assi, TestIsStudentExcluded, TestIsStudentExcluded Test Class

### Community 22 - "Scheduling & Cron Targets"
Cohesion: 0.18
Nodes (13): Scheduled Emails Table, OrderingData Dataclass, Planned Cron Targets (Wed 8PM register, Thu 3PM send), Email Idempotency (Unbuilt), Live Hosting (Public URL, Hosted Python Runtime), Scheduled Cron Triggers (Unbuilt), Unfinished Work & Planned Features, Problems Index (Bug Catalogue) (+5 more)

### Community 23 - "Database Table Tests"
Cohesion: 0.22
Nodes (5): _make_table(), Return (Table, client_mock, chain_mock) for the given table name., TestTableClear, TestTableCreate, TestTableUpdate

### Community 24 - "Switch Proposal UI"
Cohesion: 0.17
Nodes (3): supabase, switch-proposal.html — Caterer Switch Proposal Review, page

### Community 25 - "Candidate Discovery"
Cohesion: 0.29
Nodes (8): EvaluationData, find_candidates(), Return sorted ``(score, caterer_id, caterer_name)`` for eligible     replacement, Raw records loaded from the database for the evaluation pass., _build_eval_index(), Build a real EvaluationIndex from minimal test data., Verify find_candidates applies the dietary hard filter end-to-end,     not just, TestFindCandidates

### Community 26 - "Feedback & Rolling Stats"
Cohesion: 0.32
Nodes (7): _build_feedback_index(), FeedbackEntry, get_rolling_stats(), Group feedback by (session_id, caterer_id), sorted by date ascending., Return rolling-window statistics for the most recent ROLLING_WINDOW     distinct, _fb(), TestGetRollingStats

### Community 27 - "Order Batch Building"
Cohesion: 0.18
Nodes (8): build(), _CatererBatch, get_week_label(), load(), _print_summary(), register_orders.py — Snapshot student meal preferences into the Orders table.  F, Mutable working set of assignments + popularity counts for one caterer., Print a human-readable dry-run summary.

### Community 28 - "Minimum Quantity Enforcement"
Cohesion: 0.35
Nodes (6): Assignment, enforce_min_qty(), Enforce caterer per-item min-qty by dissolving under-populated items.      For e, One student's (session, item) tuple ready to write to Orders., Caterer Min-Qty Enforcement, TestEnforceMinQty

### Community 29 - "Order Constraints & Models"
Cohesion: 0.22
Nodes (11): Orders Table, Weekly Orders Table, Order Constraint Verification (order_constraints.py), POPULARITY Fallback Mode (10+ explicit preferences), register_orders.py Script, send_orders.py Script, VARIETY Fallback Mode (under 10 explicit preferences), ./run Bash Dispatcher Script (+3 more)

### Community 31 - "Variety Optimization"
Cohesion: 0.25
Nodes (5): compute_max_variety(), _find_min_qty(), Return the most distinct items we can order while still satisfying the     cater, Return the per-item minimum quantity for the given number of distinct     items,, TestComputeMaxVariety

### Community 32 - "Webapp Architecture Docs"
Cohesion: 0.20
Nodes (10): Webapp API Endpoints (api.py), Two-Tier Caching Strategy (Server + Client), On-Site Manager Page (manage.html), Student Meal Form Webapp (meals.html), Allergy-Grade Restrictions Hard Block, is_item_compatible Compatibility Check (3-step ladder), Dietary System (Taxonomy, Compatibility Checks), Dietary Restriction Taxonomy (Superset DAG) (+2 more)

### Community 33 - "Order Timing & Constraints"
Cohesion: 0.29
Nodes (9): get_next_week_dates(), Return {day_name: date} for Mon–Fri of next week., check_min_qty(), check_session_totals(), expected_eating_count(), load(), main(), order_constraints.py — Verify that registered Orders for next week:   1. Satisfy (+1 more)

### Community 34 - "Dietary Hierarchy Build"
Cohesion: 0.22
Nodes (9): RollingStats, DIETARY_HIERARCHY Data Constant, build_hierarchy(), build_hierarchy Function, DietaryHierarchy, has_opted_out Function, Pre-computed lookup tables built from the Dietary Restrictions table.      A res, Build a :class:`DietaryHierarchy` from a list of restriction records. (+1 more)

### Community 35 - "QR Email Generation"
Cohesion: 0.36
Nodes (8): format_manager_email(), manage_url(), qr_image_url(), send_qr_emails.py — Email each on-site manager their sessions' QR codes.  Groups, URL that generates a QR code PNG via the qrserver.com public API., send_qr_emails(), session_url(), SessionEntry

### Community 36 - "Manage UI Navigation"
Cohesion: 0.28
Nodes (9): backToSessions(), changeStudent(), closeMealPicker(), editAnother(), filterStudents(), loadSessionStudentsAll(), renderStudentList(), selectSession() (+1 more)

### Community 37 - "Dietary UI Compatibility"
Cohesion: 0.31
Nodes (9): Caterer Legend Tags — Definite Incompatibility Signal, Vegetarian Variant — VO Flag Creates Companion Variant Record, bestVariantSeverity(), checkCompatibility(), renderMealList(), bestVariantSeverity(), checkCompatibility(), openMealPicker() (+1 more)

### Community 38 - "Manager Override Flow"
Cohesion: 0.22
Nodes (9): eqSets(), isDirty(), loadManagerSessions(), overrideOrder(), save(), saveDietaryRequirements(), showError(), toggleDiet() (+1 more)

### Community 39 - "Meal Link Emails"
Cohesion: 0.43
Nodes (7): format_parent_email(), format_student_email(), manage_url(), meals_url(), send_meals_links.py — Email parents or students a personalised meal-preference l, send_links(), SessionLink

### Community 40 - "Caterer Data Models"
Cohesion: 0.25
Nodes (8): Caterers Table, Caterer Switch Proposals Table, Airtable Data Model (14 Tables), Manager Substitutions Table, Menu Items Table, Natural Key Naming Conventions (schema.py), Sessions Table, Caterer Switch Proposal Approve/Reject Page (switch-proposal.html)

### Community 41 - "Database Test Infrastructure"
Cohesion: 0.36
Nodes (4): _chain_mock(), Unit tests for scripts/support/database.py.  Covers:   - Record.from_row constru, Return a mock that behaves like a Supabase query builder chain.      execute_seq, TestWriteJunctionRows

### Community 42 - "Keyword Fallback System"
Cohesion: 0.29
Nodes (8): Negative Keyword Fallback — Name-Based Dietary Guess, dietary_keywords.json — Negative Keyword Fallback Data, init(), loadEditForm(), loadRestrictions(), loadTodayOrder(), renderDietList(), selectStudent()

### Community 43 - "Webapp Variant Cache"
Cohesion: 0.29
Nodes (8): buildVariantMap(), cacheGet(), cacheSet(), ensureDietMaps(), loadMenu(), loadNegativeKeywords(), setPrefTrigger(), updatePrefTrigger()

### Community 44 - "Term Boundary Logic"
Cohesion: 0.43
Nodes (3): get_term_start(), Return the start date of the current QLD school term., TestGetTermStart

### Community 45 - "Project Overview & Goals"
Cohesion: 0.29
Nodes (7): Closed-Loop Order Automation (QR→webapp→register→send), Padea Catering Automation Project Overview, Tech Stack (Airtable, Python, Static SPA, bash run script), Thursday Manual Order Bottleneck, Padea Business Context & Bottleneck, Six Partner Schools (Three Regions, Brisbane), Ordering Pipeline (register_orders + send_orders)

### Community 46 - "Error Handling Module"
Cohesion: 0.33
Nodes (5): Exception, Centralized error handling and self-healing state-capture.  Intercepts exception, Raised when an unhandled business logic constraint or assumptions validation fai, UnhandledEdgeCaseError, Package initialization for the support module.

### Community 47 - "Allergy & Constraint Rules"
Cohesion: 0.29
Nodes (7): dietary_keywords.json Negative Keywords, Problem 23: Order Constraints Duplication, Problem 25: Explicit Override Allergy Danger, is_item_compatible Function, item_incompatibility_ids Function, NEGATIVE_KEYWORDS Constant, MenuItemFields TypedDict

### Community 49 - "Meal Selection Modal"
Cohesion: 0.33
Nodes (7): closeVariantModal(), commitMealSelection(), confirmVariantModal(), openConfirm(), selectMeal(), setOrderTrigger(), updateOrderTrigger()

### Community 50 - "Edge Cases Docs"
Cohesion: 0.40
Nodes (6): One-Way Roster Lockout (Device Lock + Roster Filter), Min-Qty Enforcement (Proportional Dissolve), Edge Cases Documentation, Self-Healing & Pydantic Validation Architecture, One-Way Roster Lockout (Disappearing Dropdown), Shared Dropdown Without Auth Prank Problem

### Community 51 - "Compatibility Records"
Cohesion: 0.33
Nodes (4): item_incompatibility_ids(), Shared dietary-compatibility logic.  Used by:   - scripts/actions/register_order, Return the restriction IDs the item *definitely* violates for this     student (, Typed record models for the Padea Supabase database.  For every table we expose:

### Community 52 - "QR Code Generation"
Cohesion: 0.60
Nodes (4): generate_qr(), main(), make_session_url(), generate_qr.py — Generate QR code PNGs for each session's web app URL.  Each QR

### Community 53 - "Student Data Migration"
Cohesion: 0.40
Nodes (5): Students Source Data (students.xlsx converted), Students Table, LLM Extraction in Migration (caterer_contacts, menus, exclusions), Migration Dependency Order, Migration Pipeline (One-Shot Airtable Import)

### Community 55 - "Sandbox Safety Guards"
Cohesion: 0.50
Nodes (5): Claude Code Automation Harness, Git Guard - Unauthorized Edit Revert, Latest Error Prompt Loader, Restricted PATH Sandbox, Self-Healing Orchestration

### Community 56 - "Order Data Structures"
Cohesion: 0.40
Nodes (5): OrderingData, OrderingIndex, Pre-computed lookups derived from :class:`OrderingData`., Raw records loaded once from Airtable for the order build., ConstraintsData

### Community 58 - "Digital Ticket & Override"
Cohesion: 0.67
Nodes (3): Problem 27: Digital Ticketing Swapped Meals, override_order RPC Function, OrderFields TypedDict

### Community 59 - "LLM & Logging Utils"
Cohesion: 0.67
Nodes (3): prompt_user Tkinter Dialog, ask_llm Function, log Logger Instance

## Knowledge Gaps
- **109 isolated node(s):** `TAG_SHORT`, `CONSTRAINT_PHRASE`, `_memCache`, `ls`, `state` (+104 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **21 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Record` connect `Order Registration Pipeline` to `Dietary Hierarchy Build`, `Order Email Generation`, `Self-Healing Error Infrastructure`, `Caterer Switch Execution`, `Caterer Proposal Lifecycle`, `Caterer Scoring & Filtering`, `Database Access Layer`, `Error Handling Module`, `Meal Assignment Logic`, `Database Utilities`, `Idempotent Order Registration`, `Compatibility Records`, `Student Exclusion Check`, `User Interaction Utilities`, `Candidate Discovery`, `Minimum Quantity Enforcement`?**
  _High betweenness centrality (0.266) - this node is a cross-community bridge._
- **Why does `ask_llm()` connect `Migration & Notification` to `Error Handling Module`, `User Interaction Utilities`?**
  _High betweenness centrality (0.264) - this node is a cross-community bridge._
- **Why does `run()` connect `Migration & Notification` to `Dietary UI Compatibility`?**
  _High betweenness centrality (0.237) - this node is a cross-community bridge._
- **Are the 57 inferred relationships involving `Record` (e.g. with `DietaryHierarchy` and `.create()`) actually correct?**
  _`Record` has 57 INFERRED edges - model-reasoned connections that need verification._
- **Are the 43 inferred relationships involving `MockDatabase` (e.g. with `TestRecordFromRow` and `TestExtractJunctionFields`) actually correct?**
  _`MockDatabase` has 43 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Table` (e.g. with `TestRecordFromRow` and `TestExtractJunctionFields`) actually correct?**
  _`Table` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `register_orders()` (e.g. with `has_opted_out()` and `is_item_compatible()`) actually correct?**
  _`register_orders()` has 10 INFERRED edges - model-reasoned connections that need verification._