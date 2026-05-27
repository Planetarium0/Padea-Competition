/* switch-proposal.js — Review and act on a Caterer Switch Proposal.
 *
 * URL: /webapp/switch-proposal.html?id=<airtable_record_id>
 *
 * All Airtable access is handled server-side by host_webapp.py:
 *   GET  /api/proposal/<id>         — load proposal details
 *   POST /api/proposal/<id>/approve — execute the switch
 *   POST /api/proposal/<id>/reject  — reject with optional notes
 *
 * Requires the webapp to be served via ./run host.
 */

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------

function show(id)         { document.getElementById(id).classList.remove('hidden'); }
function hide(id)         { document.getElementById(id).classList.add('hidden'); }
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
// Main page object
// ---------------------------------------------------------------------------

const page = {
    proposalId:   null,
    sessionName:  '(session)',
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
        const res  = await fetch(`/api/proposal/${this.proposalId}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

        this.sessionName  = data.sessionName;
        this.outgoingName = data.outgoingName;
        this.incomingName = data.incomingName;

        setText('d-session',  data.sessionName);
        setText('d-outgoing', data.outgoingName);
        setText('d-incoming', data.incomingName);
        setText('d-rating',   ratingDisplay(data.avgRating));
        setText('d-sessions', data.sessionsSampled ?? '—');
        setText('d-raters',   data.uniqueRaters    ?? '—');
        setText('d-week',     formatDate(data.effectiveWeek));

        if (data.notes) {
            document.getElementById('notes-row').classList.remove('hidden');
            setText('d-notes', data.notes);
        }

        const status = data.status;
        const badge  = document.getElementById('status-badge');
        badge.textContent = status;
        badge.className   = `status-badge status-${status}`;

        if (status === 'Pending') {
            show('pending-actions');
        } else {
            const notices = {
                Approved: 'This switch is queued and will take effect at the next order run.',
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
        try {
            const res  = await fetch(`/api/proposal/${this.proposalId}/approve`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

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
        const notes = document.getElementById('reject-reason').value.trim();
        try {
            const res  = await fetch(`/api/proposal/${this.proposalId}/reject`, {
                method:  'POST',
                headers: { 'Content-Type': 'application/json' },
                body:    JSON.stringify({ notes }),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

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
