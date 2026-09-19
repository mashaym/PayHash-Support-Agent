import { useEffect, useRef } from 'react';

function Message({ speaker, children }) {
  return (
    <div className={`message message-${speaker}`}>
      <span className="message-label">{speaker === 'user' ? 'You' : 'PayHash'}</span>
      <div className="message-bubble">{children}</div>
    </div>
  );
}

export default function ChatConversation({ history, pendingQuestion }) {
  const scrollArea = useRef(null);

  // An effect runs after React updates the DOM, when the new message has a height.
  useEffect(() => {
    scrollArea.current.scrollTop = scrollArea.current.scrollHeight;
  }, [history, pendingQuestion]);

  return (
    <div className="conversation" ref={scrollArea} role="log" aria-label="Conversation" aria-live="polite" aria-relevant="additions text" tabIndex={0}>
      <div className="conversation-start"><span />YOUR CONVERSATION<span /></div>
      <Message speaker="assistant">Hi, I'm your PayHash assistant. I can help with wallet questions, check a transaction, or connect you with human support. What's on your mind?</Message>
      {history.map((turn) => (
        <div className="exchange" key={turn.id}>
          <Message speaker="user">{turn.question}</Message>
          <Message speaker="assistant">{turn.answer}</Message>
        </div>
      ))}
      {pendingQuestion !== null && (
        <>
          <Message speaker="user">{pendingQuestion}</Message>
          <div className="thinking" role="status"><span className="thinking-dot" aria-hidden="true" />Thinking...</div>
        </>
      )}
    </div>
  );
}
