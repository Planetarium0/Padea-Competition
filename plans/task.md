# Tasks

## Phase 1: Schema + Order Engine
- [x] Add Weekly Orders + Order Line Items tables to `scripts/schema.py`
- [x] Run `./run schema update` to sync new tables
- [x] Create `scripts/generate_orders.py` — core order compilation
- [x] Add `orders` commands to `run` script
- [ ] Test with `--dry-run` against live Airtable data

## Phase 2: Student Web App
- [x] Create `output/webapp/index.html` — SPA shell
- [x] Create `output/webapp/style.css` — mobile-first premium design
- [x] Create `output/webapp/app.js` — Airtable API integration
- [ ] Browser test the web app locally

## Phase 3: Email + QR
- [x] Create `scripts/send_orders.py` — email formatting + logging
- [x] Create `scripts/generate_qr.py` — QR code generation
- [x] Add `qr` command to `run` script
- [ ] Test email output in `output/emails/`

## Phase 4: Verification
- [ ] End-to-end dry run walkthrough
- [ ] Review generated emails against expected format
