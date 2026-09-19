import { useRef, useState } from 'react';
import { sendChat } from './api.js';
import ChatConversation from './components/ChatConversation.jsx';
import ChatComposer from './components/ChatComposer.jsx';

const MAX_HISTORY_TURNS = 10;
const STARTERS = [
  ['Transfers & fees', 'What is the fee for a domestic bank transfer?'],
  ['Track a transaction', 'What is the status of TXN100235?'],
  ['Account verification', 'What are the KYC requirements?'],
];

export default function App() {
  // State survives re-renders. Updating it tells React to update the screen.
  const [history, setHistory] = useState([]);
  const [draft, setDraft] = useState('');
  const [pendingQuestion, setPendingQuestion] = useState(null);
  const [error, setError] = useState('');
  const requestInFlight = useRef(false);
  const isLoading = pendingQuestion !== null;

  async function handleSend() {
    const message = draft.trim();
    if (!message || requestInFlight.current) return;

    // This ref guards against duplicate submissions before React renders again.
    requestInFlight.current = true;
    setPendingQuestion(message);
    setError('');
    try {
      const reply = await sendChat(message, history);
      // Add complete pairs only. Never send failed replies or the pending question as history.
      const exchange = { id: crypto.randomUUID(), question: message, answer: reply };
      setHistory((previous) => [...previous, exchange].slice(-MAX_HISTORY_TURNS));
      setDraft('');
    } catch (problem) {
      setError(problem.message);
    } finally {
      requestInFlight.current = false;
      setPendingQuestion(null);
    }
  }

  function handleReset() {
    if (requestInFlight.current) return;
    setHistory([]);
    setDraft('');
    setError('');
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="/" aria-label="PayHash support home">
          <span className="brand-mark" aria-hidden="true">P<span>&bull;</span></span>
          PayHash<span className="brand-divider" /> <span className="brand-area">Support</span>
        </a>
        <span className="demo-badge">Demo wallet</span>
      </header>

      <main className="support-layout">
        <aside className="intro">
          <p className="eyebrow">A LITTLE HELP, RIGHT HERE</p>
          <h1>Let's make<br /> things simple.</h1>
          <p className="intro-copy">Questions about your wallet?<br />We'll help you find your next step.</p>
          <div className="help-topics" aria-label="Suggested questions">
            <p className="section-label">START WITH A QUESTION</p>
            {STARTERS.map(([label, question]) => (
              <button key={label} type="button" disabled={isLoading} onClick={() => setDraft(question)}>
                {label}<span aria-hidden="true">&#8599;</span>
              </button>
            ))}
          </div>
          <div className="privacy-note">
            <span className="note-symbol" aria-hidden="true">&#10035;</span>
            <p>A little reminder<br /><span>Keep your PIN, password, and OTP private.</span></p>
          </div>
        </aside>

        <section className="chat-panel" aria-label="Support chat">
          <header className="chat-header">
            <div className="assistant-avatar" aria-hidden="true">P</div>
            <div className="chat-title"><h2>PayHash Assistant</h2><p>Your wallet questions, answered</p></div>
            <button className="reset-button" type="button" onClick={handleReset} disabled={isLoading || (!history.length && !draft && !error)}>New chat</button>
          </header>

          <ChatConversation history={history} pendingQuestion={pendingQuestion} />
          {error && <div className="error-message" role="alert">{error} Your message is still below.</div>}
          <ChatComposer draft={draft} onDraftChange={setDraft} onSend={handleSend} isLoading={isLoading} />
          <p className="chat-footnote">AI support for a fictional wallet. This chat remembers the latest 10 exchanges.</p>
        </section>
      </main>
      <footer className="site-footer"><span>PAYHASH / SUPPORT</span><span>A little clarity goes a long way.</span></footer>
    </div>
  );
}
