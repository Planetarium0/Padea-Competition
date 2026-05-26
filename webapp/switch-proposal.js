/* switch-proposal.js — Review and act on a Caterer Switch Proposal.
 *
 * URL: /webapp/switch-proposal.html?id=<airtable_record_id>
 *
 * On Approve: performs the same mutations as execute_caterer_switch.py —
 *   sets Sessions.Incoming Caterer, updates Caterers.Able to Serve Schools,
 *   clears Students.Meal Preference — then marks the proposal Executed.
 *   register_orders.py commits the final Caterer → Incoming Caterer flip at
 *   the next Wednesday 8 PM run.
 *
 * On Reject: sets Status='Rejected' with optional coordinator notes.
 *
 * Requires CONFIG.API_KEY to have write access to:
 *   Caterer Switch Proposals, Sessions, Caterers, Students
 */

// ---------------------------------------------------------------------------
// Airtable helpers
// ---------------------------------------------------------------------------

const AT_BASE = `https://api.airtable.com/v0/${CONFIG.BASE_ID}`;

function atHeaders() {
    return {
        'Authorization': `Bearer ${CONFIG.API_KEY}`,
        'Content-Type': 'application/json',
    };
}

async function atGetOne(table, id) {
    const res = await fetch(`${AT_BASE}/${enc(table)}/${id}`, { headers: atHeaders() });
    if (!res.ok) throw new Error(`GET ${table}/${id} → ${res.status}`);
    return res.json();
}

async function atGetAll(table, formula = null) {
    const records = [];
    let offset = null;
    do {
        let url = `${AT_BASE}/${enc(table)}?pageSize=100`;
        if (formula) url += `&filterByFormula=${enc(formula)}`;
        if (offset)  url += `&offset=${offset}`;
        const res = await fetch(url, { headers: atHeaders() });
        if (!res.ok) throw new Error(`GET ${table} → ${res.status}`);
        const json = await res.json();
        records.push(...json.records);
        offset = json.offset ?? null;
    } while (offset);
    return records;
}

async function atPatch(table, id, fields) {
    const res = await fetch(`${AT_BASE}/${enc(table)}/${id}`, {
        method: 'PATCH',
        headers: atHeaders(),
        body: JSON.stringify({ fields }),
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(`PATCH ${table}/${id} → ${res.status}: ${text}`);
    }
    return res.json();
}

async function atPatchBatch(table, updates) {
    // updates: [{id, fields}, ...]  max 10 per request
    for (let i = 0; i < updates.length; i += 10) {
        const batch = updates.slice(i, i + 10);
        const res = await fetch(`${AT_BASE}/${enc(table)}`, {
            method: 'PATCH',
            headers: atHeaders(),
            body: JSON.stringify({
                records: batch.map(u => ({ id: u.id, fields: u.fields })),
            }),
        });
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`PATCH ${table} batch → ${res.status}: ${text}`);
        }
    }
}

function enc(s) { return encodeURIComponent(s); }

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }
function setText(id, val) { document.getElementById(id).textContent = val; }

function showOnly(id) {
    ['view-loading', 'view-proposal', 'view-reject',
     'view-working', 'view-done', 'view-error'].forEach(v => {
        document.getElementById(v).classList.toggle('hidden', v !== id);
    });
}

function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('en-AU', { day: 'numeric', month: 'long', year: 'numeric' });
}

function ratingDisplay(avg) {
    if (avg == null) return '—';
    const full  = Math.round(avg);
    const stars = '★'.repeat(full) + '☆'.repeat(5 - full);
    return `${avg.toFixed(1)} / 5  ${stars}`;
}

// ---------------------------------------------------------------------------
// Confirm modal
// ---------------------------------------------------------------------------

let _confirmCallback = null;

function openConfirm({ title, body, confirmLabel, onConfirm }) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-body').textContent  = body;
    document.getElementById('confirm-yes').textContent   = confirmLabel || 'OK';
    _confirmCallback = onConfirm;
    document.getElementById('confirm-modal').classList.remove('hidden');
}

function closeConfirm() {
    document.getElementById('confirm-modal').classList.add('hidden');
    _confirmCallback = null;
}

window.confirmModalYes = () => { if (_confirmCallback) _confirmCallback(); };
window.confirmModalNo  = () => closeConfirm();

// ---------------------------------------------------------------------------
// Progress-step helpers (used during the approve flow)
// ---------------------------------------------------------------------------

const STEPS = [
    { id: 'step-sessions',  label: 'Queuing caterer change on session'   },
    { id: 'step-caterers',  label: 'Updating caterer eligibility'        },
    { id: 'step-students',  label: 'Clearing student meal preferences'   },
    { id: 'step-finalise',  label: 'Finalising proposal'                 },
];

function initProgress() {
    const list = document.getElementById('progress-list');
    list.innerHTML = STEPS.map(s => `
        <li class="progress-item pi-pending" id="${s.id}">
            <span class="pi-icon">·</span>
            <span>${s.label}</span>
        </li>`).join('');
}

function stepWorking(id) {
    const el = document.getElementById(id);
    el.className = 'progress-item pi-working';
    el.querySelector('.pi-icon').innerHTML = '<div class="spinner"></div>';
}

function stepDone(id) {
    const el = document.getElementById(id);
    el.className = 'progress-item pi-done';
    el.querySelector('.pi-icon').textContent = '✓';
}

// ---------------------------------------------------------------------------
// Main page object
// ---------------------------------------------------------------------------

const page = {
    proposalId:   null,
    proposal:     null,
    sessionId:    null,
    sessionName:  '(session)',
    schoolId:     null,
    outgoingId:   null,
    incomingId:   null,
    outgoingName: '(outgoing caterer)',
    incomingName: '(incoming caterer)',

    async init() {
        const params = new URLSearchParams(location.search);
        this.proposalId = params.get('id');
        if (!this.proposalId) {
            return this.showError(
                'No proposal ID found in URL.\n' +
                'Expected: switch-proposal.html?id=recXXXXXXXXXXXXXX'
            );
        }
        try {
            await this.loadProposal();
        } catch (e) {
            this.showError(e.message);
        }
    },

    async loadProposal() {
        const rec = await atGetOne('Caterer Switch Proposals', this.proposalId);
        this.proposal   = rec;
        const f = rec.fields;

        this.sessionId  = (f['Session']          || [])[0] ?? null;
        this.outgoingId = (f['Outgoing Caterer']  || [])[0] ?? null;
        this.incomingId = (f['Incoming Caterer']  || [])[0] ?? null;

        // Fetch session and caterers in parallel; then fetch school from session.
        const [sessionRec, outgoing, incoming] = await Promise.all([
            this.sessionId  ? atGetOne('Sessions', this.sessionId)   : null,
            this.outgoingId ? atGetOne('Caterers', this.outgoingId)  : null,
            this.incomingId ? atGetOne('Caterers', this.incomingId)  : null,
        ]);

        this.schoolId = (sessionRec?.fields?.['School'] || [])[0] ?? null;
        const schoolRec = this.schoolId ? await atGetOne('Schools', this.schoolId) : null;
        const schoolName = schoolRec?.fields?.['School Name'] ?? '—';
        const day = sessionRec?.fields?.['Day'] ?? '';
        this.sessionName = day ? `${schoolName} — ${day}` : schoolName;

        this.outgoingName = outgoing?.fields?.['Caterer Name'] ?? '—';
        this.incomingName = incoming?.fields?.['Caterer Name'] ?? '—';

        setText('d-session',  this.sessionName);
        setText('d-outgoing', this.outgoingName);
        setText('d-incoming', this.incomingName);
        setText('d-rating',   ratingDisplay(f['Avg Rating']));
        setText('d-sessions', f['Sessions Sampled'] ?? '—');
        setText('d-raters',   f['Unique Raters']    ?? '—');
        setText('d-week',     formatDate(f['Effective Week']));

        if (f['Notes']) {
            document.getElementById('notes-row').classList.remove('hidden');
            setText('d-notes', f['Notes']);
        }

        // Badge + actions
        const status = f['Status'] || 'Pending';
        const badge  = document.getElementById('status-badge');
        badge.textContent = status;
        badge.className   = `status-badge status-${status}`;

        if (status === 'Pending') {
            show('pending-actions');
        } else {
            const notices = {
                Approved: 'This proposal has been approved. Run ./run switch to execute the switch.',
                Rejected: 'This proposal was rejected.',
                Executed: 'This switch has already been executed.',
            };
            const notice = document.getElementById('readonly-notice');
            notice.textContent = notices[status] ?? `Status: ${status}`;
            show('readonly-notice');
        }

        showOnly('view-proposal');
    },

    // -----------------------------------------------------------------------
    // Approve flow
    // -----------------------------------------------------------------------

    approve() {
        openConfirm({
            title:        'Approve switch?',
            body:         `Switch from ${this.outgoingName} to ${this.incomingName} ` +
                          `for ${this.sessionName}? This will update the session and ` +
                          `clear student meal preferences.`,
            confirmLabel: 'Approve',
            onConfirm:    () => { closeConfirm(); this._doApprove(); },
        });
    },

    async _doApprove() {
        showOnly('view-working');
        initProgress();

        try {
            // --- Step 1: Set Sessions.Incoming Caterer ----------------------
            stepWorking('step-sessions');
            await atPatch('Sessions', this.sessionId, {
                'Incoming Caterer': [this.incomingId],
            });
            stepDone('step-sessions');

            // --- Step 2: Update Caterers.Able to Serve Schools --------------
            // Outgoing caterer gains the school back as eligible;
            // incoming caterer loses it (it's now actively serving).
            stepWorking('step-caterers');
            const [outRec, inRec] = await Promise.all([
                atGetOne('Caterers', this.outgoingId),
                atGetOne('Caterers', this.incomingId),
            ]);
            const outAble = outRec.fields['Able to Serve Schools'] || [];
            const inAble  = inRec.fields['Able to Serve Schools']  || [];
            await Promise.all([
                atPatch('Caterers', this.outgoingId, {
                    'Able to Serve Schools': [...new Set([...outAble, this.schoolId])],
                }),
                atPatch('Caterers', this.incomingId, {
                    'Able to Serve Schools': inAble.filter(id => id !== this.schoolId),
                }),
            ]);
            stepDone('step-caterers');

            // --- Step 3: Clear Students.Meal Preference ---------------------
            stepWorking('step-students');
            const allStudents = await atGetAll('Students');
            const affected = allStudents.filter(stu =>
                (stu.fields['Sessions'] || []).includes(this.sessionId)
            );
            if (affected.length > 0) {
                await atPatchBatch('Students', affected.map(stu => ({
                    id:     stu.id,
                    fields: { 'Meal Preference': [] },
                })));
            }
            stepDone('step-students');

            // --- Step 4: Mark proposal Executed -----------------------------
            stepWorking('step-finalise');
            await atPatch('Caterer Switch Proposals', this.proposalId, {
                Status: 'Executed',
            });
            stepDone('step-finalise');

            document.getElementById('result-icon').className = 'result-icon icon-success';
            document.getElementById('result-icon').textContent = '✓';
            setText('result-title', 'Switch approved!');
            setText('result-msg',
                `${this.incomingName} will take over from ${this.outgoingName} ` +
                `for ${this.sessionName} from the next order run.`
            );
            showOnly('view-done');

        } catch (e) {
            this.showError(`Error during approval:\n${e.message}`);
        }
    },

    // -----------------------------------------------------------------------
    // Reject flow
    // -----------------------------------------------------------------------

    showRejectForm() {
        document.getElementById('reject-reason').value = '';
        showOnly('view-reject');
    },

    cancelReject() {
        showOnly('view-proposal');
    },

    async confirmReject() {
        const reason = document.getElementById('reject-reason').value.trim();
        try {
            const fields = { Status: 'Rejected' };
            if (reason) fields['Notes'] = reason;
            await atPatch('Caterer Switch Proposals', this.proposalId, fields);

            document.getElementById('result-icon').className = 'result-icon icon-rejected';
            document.getElementById('result-icon').textContent = '✕';
            setText('result-title', 'Proposal rejected');
            setText('result-msg',
                `You won't be reminded about ${this.outgoingName} for ` +
                `${this.sessionName} again this term.`
            );
            showOnly('view-done');
        } catch (e) {
            this.showError(`Failed to save rejection:\n${e.message}`);
        }
    },

    // -----------------------------------------------------------------------
    // Error
    // -----------------------------------------------------------------------

    showError(msg) {
        setText('error-msg', msg);
        showOnly('view-error');
    },
};

page.init();
