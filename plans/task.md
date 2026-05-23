# Tasks

## Phase 1: Schema + Order Engine
- [ ] Add Weekly Orders + Order Line Items tables to `scripts/schema.py`
- [ ] Run `./run schema update` to sync new tables
- [ ] Create `scripts/generate_orders.py` — core order compilation
- [ ] Add `orders` commands to `run` script
- [ ] Test with `--dry-run` against live Airtable data

## Phase 2: Student Web App
- [ ] Create `output/webapp/index.html` — SPA shell
- [ ] Create `output/webapp/style.css` — mobile-first premium design
- [ ] Create `output/webapp/app.js` — Airtable API integration
- [ ] Browser test the web app locally

## Phase 3: Email + QR
- [ ] Create `scripts/send_orders.py` — email formatting + logging
- [ ] Create `scripts/generate_qr.py` — QR code generation
- [ ] Test email output in `output/emails/`

## Phase 4: Verification
- [ ] End-to-end dry run walkthrough
- [ ] Review generated emails against expected format
