const CHAT_URL = 'http://127.0.0.1:8000/chat';

export async function sendChat(message, history) {
  let response;
  try {
    response = await fetch(CHAT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        // UI IDs identify rendered messages; the backend only needs text pairs.
        history: history.map(({ question, answer }) => ({ question, answer })),
      }),
    });
  } catch {
    throw new Error('Could not reach support. Check your connection and try again.');
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // Validation errors have an array of details; don't display raw objects.
    const detail = typeof data?.detail === 'string' ? data.detail : null;
    throw new Error(detail || 'Your message could not be processed. Please try again.');
  }
  if (typeof data?.reply !== 'string' || !data.reply.trim()) {
    throw new Error('Support returned an empty or unexpected response. Please try again.');
  }
  return data.reply;
}
