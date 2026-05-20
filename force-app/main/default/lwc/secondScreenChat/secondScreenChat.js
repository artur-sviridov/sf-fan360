/**
 * secondScreenChat LWC
 * --------------------
 * Public second-screen page. Three panes:
 *   - top: live score strip subscribed to a Platform Event
 *   - middle: chat with the Broadcast Metadata Agent
 *   - bottom: trending question carousel
 *
 * Agent invocation goes through Apex `SecondScreenChatController.ask`,
 * which calls the Agentforce Conversation API server-side so the
 * browser never sees an org access token.
 */

import { LightningElement, api, track } from 'lwc';
import { subscribe, onError } from 'lightning/empApi';
import askAgent from '@salesforce/apex/SecondScreenChatController.ask';
import latestSnapshot from '@salesforce/apex/SecondScreenChatController.latestSnapshot';

const LIVE_EVENT_CHANNEL = '/event/LiveMatchEvent__e';

const TRENDING_PROMPTS = [
    'Has anyone scored more goals against Chelsea than Salah?',
    'Why did Arsenal switch to a back five against Liverpool in 2024?',
    'Who has the highest xG in the current match?',
    'Liverpool vs Manchester City head-to-head over the last 10 years.',
    'Explain Pep Guardiola\u2019s false-nine setup at Manchester City.'
];

export default class SecondScreenChat extends LightningElement {
    @api agentApiName = 'Broadcast_Metadata_Agent';
    @api favoriteTeam = '';

    @track messages = [];
    @track pendingInput = '';
    @track isThinking = false;
    @track liveSnapshot = { isLive: false };

    trendingPrompts = TRENDING_PROMPTS;
    _subscription = null;
    _nextId = 1;

    connectedCallback() {
        this.refreshSnapshot();
        this._setupLiveSubscription();
    }

    disconnectedCallback() {
        if (this._subscription) {
            try {
                window.dispatchEvent(new CustomEvent('emp-unsubscribe', { detail: this._subscription }));
            } catch (_e) {
                // ignore
            }
        }
    }

    handleInputChange(event) {
        this.pendingInput = event.target.value;
    }

    handleTrendingClick(event) {
        const prompt = event.currentTarget.dataset.prompt;
        this.pendingInput = prompt;
        this._dispatchAsk(prompt);
    }

    handleSend(event) {
        event.preventDefault();
        const text = (this.pendingInput || '').trim();
        if (!text) {
            return;
        }
        this._dispatchAsk(text);
    }

    async _dispatchAsk(text) {
        const userMsg = this._appendMessage({ author: 'user', body: text });
        this.pendingInput = '';
        this.isThinking = true;
        try {
            const reply = await askAgent({
                agentApiName: this.agentApiName,
                utterance: text,
                favoriteTeam: this.favoriteTeam
            });
            this._appendMessage({
                author: 'agent',
                body: reply?.body || 'Sorry, no response.',
                citation: reply?.citation,
                citationUrl: reply?.citationUrl
            });
        } catch (error) {
            this._appendMessage({
                author: 'agent',
                body: 'I had a problem reaching the agent. Try again in a moment.',
                error: true
            });
            // eslint-disable-next-line no-console
            console.error('agent error', error);
        } finally {
            this.isThinking = false;
        }
    }

    _appendMessage({ author, body, citation, citationUrl, error }) {
        const msg = {
            id: this._nextId++,
            author,
            body,
            citation,
            citationUrl,
            cssClass: `message ${author}${error ? ' error' : ''}`
        };
        this.messages = [...this.messages, msg];
        return msg;
    }

    async refreshSnapshot() {
        try {
            const snap = await latestSnapshot();
            if (snap) {
                this.liveSnapshot = snap;
            }
        } catch (err) {
            // best-effort; the chat still works without live snapshot.
            this.liveSnapshot = { isLive: false };
        }
    }

    _setupLiveSubscription() {
        const messageCallback = () => {
            this.refreshSnapshot();
        };
        subscribe(LIVE_EVENT_CHANNEL, -1, messageCallback)
            .then((response) => {
                this._subscription = response;
            })
            .catch(() => {
                // Live channel optional; refresh on a poll instead.
                this._pollHandle = setInterval(() => this.refreshSnapshot(), 60000);
            });
        onError(() => {
            this.refreshSnapshot();
        });
    }
}
