import { useEffect, useRef } from 'react';

export default function ChatComposer({ draft, onDraftChange, onSend, isLoading }) {
  const input = useRef(null);

  useEffect(() => {
    if (!isLoading) input.current.focus();
  }, [isLoading]);

  function handleSubmit(event) {
    event.preventDefault(); // A chat send should not reload the browser page.
    onSend();
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (!isLoading && draft.trim()) event.currentTarget.form.requestSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <label className="sr-only" htmlFor="message">Message PayHash</label>
      <div className="composer-field">
        <textarea id="message" ref={input} rows={2} value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          onKeyDown={handleKeyDown} disabled={isLoading}
          placeholder="How can we help you today?" aria-describedby="composer-hint" />
        <button className="send-button" type="submit" disabled={isLoading || !draft.trim()}>
          Send <span aria-hidden="true">&#8593;</span>
        </button>
      </div>
      <p id="composer-hint">Enter to send <span>&middot;</span> Shift + Enter for a new line</p>
    </form>
  );
}
