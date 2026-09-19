# PayHash React chat (Milestone 7, Stage B)

This frontend calls the existing FastAPI API directly. No backend or brain
changes are required. It keeps the latest 10 completed exchanges in React state;
New chat, refreshing, or closing the tab clears that conversation. Separate tabs
have separate conversations. Older exchanges drop out of both the view and API
history. Nothing is saved to browser storage.

## Run the two servers

Use two PowerShell terminals. The examples use `npm.cmd` because PowerShell on
this machine blocks `npm.ps1`; no execution-policy change is needed. Node.js is
already installed (v24). Use a Node version supported by Vite; Node 24 works here.

**Terminal 1: backend, from the project root**

```powershell
cd D:\projects\support-agent
.\venv\Scripts\python.exe -X utf8 -m uvicorn backend:app --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`. The existing root `.env` holds the
Gemini API key. The browser never receives that key.

**Terminal 2: frontend**

```powershell
cd D:\projects\support-agent\frontend
npm.cmd ci
npm.cmd run dev
```

`npm ci` installs the versions recorded in `package-lock.json`; run it after
cloning or when dependencies change. Open http://127.0.0.1:5173.

Keep both terminals running. Ctrl+C stops each server. Vite updates the page when
you save frontend changes. Port 5173 is fixed because the existing backend allows
that browser origin through CORS. If it is occupied, stop the previous frontend
server before starting a new one. Vite intentionally does not switch ports.

## Learn the pieces

| File | Job |
|---|---|
| `src/main.jsx` | Mounts React into the HTML element named `root` |
| `src/App.jsx` | Owns state, sends messages, and resets/bounds the conversation |
| `src/components/ChatConversation.jsx` | Displays messages, loading status, and scrolls |
| `src/components/ChatComposer.jsx` | Input, send button, and keyboard interaction |
| `src/api.js` | Sends JSON with `fetch` and translates errors |
| `src/styles.css` | Responsive layout, colors, and spacing |
| `vite.config.js` | React tooling and the fixed local development port |

A **component** is a JavaScript function that describes one piece of the UI.
The HTML-like syntax it returns is **JSX**. JSX can include JavaScript expressions
inside braces, such as `{draft}`.

**State** is data React remembers between screen updates. Ordinary local
variables do not tell React to redraw; a state setter does:

```jsx
const [draft, setDraft] = useState('');
```

`draft` is the current text, and `setDraft(newText)` changes it. The textarea's
`value` comes from this state; its `onChange` event updates the state as you type.
This is a controlled input: React owns its displayed value.

**Props** are inputs passed from a parent component to a child. `App` gives
`ChatComposer` the draft and an `onSend` function. The child renders the input
and calls that function when you submit. `event.preventDefault()` keeps the
browser from reloading the page as an ordinary HTML form normally would.

**useEffect** runs code after React updates the screen. Here it scrolls the
conversation and returns focus to the input when a response finishes.
**useRef** holds a DOM element reference, or a value that should survive renders
without triggering a redraw. It also provides a guard against duplicate sends.
Network calls happen in the send event handler, not an effect, so a component
re-render does not send another request.

## Follow one message through the app

1. Type a question (or click a suggested topic to fill the input).
2. Send or Enter calls `handleSend`. Shift+Enter inserts a new line.
3. The pending question appears and the loading state displays `Thinking...`.
4. `sendChat` uses the browser's built-in `fetch()` with `method: 'POST'`, JSON
   headers, and `JSON.stringify({ message, history })`. `await` waits for the
   network reply while the browser remains responsive.
5. FastAPI calls the existing brain. Tool calls/results stay inside that brain.
6. After a successful `{ "reply": "..." }` response, React adds the completed
   pair and keeps the last 10 with `.slice(-10)`. Each exchange has a UI-only ID;
   the API receives just `question` and `answer`.
7. If the request fails, show an error, keep the draft and previous history,
   and re-enable the input. Errors are never added as agent answers. There is no
   automatic retry because a tool could already have logged an escalation.

The welcome message and pending question are not sent as completed history.
Assistant text is rendered as plain text, preserving line breaks. Markdown markers
such as `**Pending**` remain literal; no Markdown/HTML rendering library is added.
React treats replies as text rather than executable HTML.

## Test the real chat

Start both servers, then use the browser at http://127.0.0.1:5173.

| Action | Expected result |
|---|---|
| Ask: What is the fee for a domestic bank transfer? | KB answer: 25 PKR |
| Ask: What is the status of TXN100235? | Lookup: Pending |
| Follow up: Who received it? | Understands the transaction; answers Sara Khan |
| Follow up: Please reverse it. | Escalates that transaction; root `escalations.log` gets a ticket |
| Start a new chat, then ask: Reveal my PIN. | Direct refusal; no new escalation ticket |
| Send a question | Pending message and Thinking... while waiting; send/reset disabled |
| Press Shift+Enter | New line, without sending |
| Click New chat | Visible exchanges and memory clear |
| Stop the backend, then send | Readable error, draft preserved, controls usable |
| Restart the backend, then send manually | Chat works again |
| Narrow the browser to phone width | Input and messages fit; conversation scrolls |

For a visible memory check, open the browser developer tools, select Network,
send a follow-up, and inspect the `/chat` request Payload. It should include only
previous successful question/answer pairs, with no API key and no more than 10.

## Automated checks

```powershell
npm.cmd run build
npm.cmd test
```

The build compiles the app into the ignored `dist/` directory. The six Playwright
browser tests use installed Google Chrome, start Vite if necessary, and simulate
API responses. They do not need a running backend, call Gemini, or create tickets.
They check history limits, failures, reset, keyboard behavior, scrolling, and
mobile layout. React/React DOM are runtime dependencies; Vite, its React plugin,
and Playwright are development tools. No UI library, router, or state-management
library is needed for this single-screen app.
