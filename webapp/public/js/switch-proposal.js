/* switch-proposal.js — Review and act on a Caterer Switch Proposal.
 *
 * URL: /webapp/switch-proposal.html?id=<proposal_uuid>
 *
 * All data access goes directly to Supabase via supabase-js.
 */

import { supabase } from './shared/supabase_client.js'
import { openConfirm, closeConfirm, confirmModalYes, confirmModalNo } from './shared/ui.js'

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
                'Expected: switch-proposal.html?id=<uuid>'
            );
        }
        try {
            await this.loadProposal();
        } catch (e) {
            this.showError(e.message);
        }
    },

    async loadProposal() {
        const { data: prop, error } = await supabase
            .from('caterer_switch_proposals')
            .select(`
              *,
              sessions(session_code, schools(name)),
              caterers_out:caterers!outgoing_caterer_id(name),
              caterers_in:caterers!incoming_caterer_id(name)
            `)
            .eq('id', this.proposalId)
            .single();
        if (error || !prop) throw new Error('Proposal not found');

        this.sessionName  = prop.sessions ? `${prop.sessions.schools?.name || '?'} — ${prop.sessions.session_code || ''}` : '—';
        this.outgoingName = prop.caterers_out?.name || '—';
        this.incomingName = prop.caterers_in?.name  || '—';

        setText('d-session',  this.sessionName);
        setText('d-outgoing', this.outgoingName);
        setText('d-incoming', this.incomingName);
        setText('d-rating',   ratingDisplay(prop.avg_rating));
        setText('d-sessions', prop.sessions_sampled ?? '—');
        setText('d-raters',   prop.unique_raters    ?? '—');
        setText('d-week',     formatDate(prop.effective_week));

        if (prop.notes) {
            document.getElementById('notes-row').classList.remove('hidden');
            setText('d-notes', prop.notes);
        }

        const status = prop.status || 'Pending';
        const badge  = document.getElementById('status-badge');
        badge.textContent = status;
        badge.className   = `status-badge status-${status}`;

        if (status === 'Pending') {
            show('pending-actions');
        } else {
            const notices = {
                Approved: 'This switch is queued and will take effect at the next order run.',
                Rejected:  'This proposal was rejected.',
                Executed:  'This switch has already been executed.',
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
            const { error } = await supabase.rpc('approve_caterer_switch', { p_proposal_id: this.proposalId });
            if (error) throw new Error(error.message);

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
            const fields = { status: 'Rejected' };
            if (notes) fields.notes = notes;
            const { error } = await supabase
                .from('caterer_switch_proposals')
                .update(fields)
                .eq('id', this.proposalId);
            if (error) throw new Error(error.message);

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

// Expose globals so onclick attributes in HTML work with module scripts.
window.page = page;
window.confirmModalYes = confirmModalYes;
window.confirmModalNo = confirmModalNo;

page.init();
