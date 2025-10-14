# Chat Responses → Markdown → Styled HTML (Streaming‑safe)

- This README documents the feature that makes assistant replies render like ChatGPT: the model streams Markdown, and the UI turns that into styled HTML—without breaking streaming or security.

## What changed (high level)

### Gateway (FastAPI) — SSE framing fixed

- We now emit one SSE event per chunk and put multiple data: lines inside that single event. This preserves the model’s original newlines exactly as the SSE spec intends. Function: _sse_event_from_text(...).

### Chainlit UI — SSE parser + streaming

- A tiny, spec‑compliant SSE parser collects consecutive data: lines, joins them with \n, and yields one message per event. It trims at most one space after data: so tokens that start with a space (e.g., " world") keep their spacing. No more “ChooseAforspeed…” glitches.

- The UI now streams the event as‑is (no forced newline per event). Chainlit handles Markdown → HTML by default.

### Styling

- light CSS to make code blocks, tables, and blockquotes cleaner—kept modular under /public/markdown-theme.css and loaded from config.toml. HTML remains sanitized.

## Why we needed this

- Models output Markdown with line breaks. Our old stream split on \n and sent one SSE event per line; the UI then tried to re‑add newlines and trimmed leading spaces. That caused two classes of bugs:

- “poem mode” (one word per line) when the client added \n after every tiny event, and

- “words‑glued‑together” when the parser used .lstrip() and removed real leading spaces from tokens.
The fix restores spec‑compliant SSE framing plus a strict parser that preserves spacing.

## How it works (end‑to‑end)

```
Model → Gateway (chunks) → SSE:
  event: message
  data: <line 1 of chunk>
  data: <line 2 of chunk>
  
  ... (blank line = end of the event)

Browser → Chainlit:
  parse SSE → join data-lines with "\n" → msg.stream_token(exact_text)
  Chainlit renders Markdown → HTML
```

### Gateway streaming

- _sse_event_from_text normalizes \r\n → \n, then builds one SSE event with multiple data: lines so all original newlines survive. The stream also uses typed events (policy, error, done) for moderation and lifecycle.

### UI streaming

- iter_sse_events(...) collects data: lines until a blank line, then yields (event, data). Importantly, it removes only a single syntax space after data: and preserves all other whitespace. The handler appends tokens with await .
- out.stream_token(data)—no artificial newline injection.

### Rendering

- Chainlit already renders Markdown to HTML; we keep unsafe_allow_html=false for safety, and we add a small CSS theme for code/tables if desired.

## Source layout & key files

### Gateway

- apps/gateway-fastapi/src/main.py — SSE event builder _sse_event_from_text, event: policy/error/done, and the streaming loop. Also wires profiles, threads, and transcript.

### UI (Chainlit)

- apps/chainlit-ui/src/sse_utils.py — spec‑compliant SSE parser that preserves spaces/newlines.

- apps/chainlit-ui/src/main.py — streaming handler that appends tokens as‑is; shows moderation notices and errors.

### Styling / Config

- apps/chainlit-ui/src/public/markdown-theme.css — optional CSS for code blocks, tables, blockquotes, and headings.

- apps/chainlit-ui/config.toml — enables custom CSS (and keeps HTML sanitization).

## Behavior details

### Event types

- default (message): chunk text as Markdown.

- policy: moderation notice (UI shows a “Safety notice”).

- error: transient errors emitted mid‑stream.

- done: terminator event (UI stops reading).
Implemented in the Gateway and consumed in the UI stream loop.

### Security

- We did not enable raw HTML. unsafe_allow_html=false remains in config.toml. Rendering is Markdown → HTML with Chainlit’s built‑in renderer; CSS is cosmetic only.

## UI smoke prompts

- Write a short doc with # Title, ## Section, a bullet list, and a numbered list.

- Show a Python example in a fenced block and an inline code snippet.

- Give a 3-row table comparing A/B/C and a short quote.

#### All should render as normal headings, bullets, code blocks, tables, and quotes—with correct spacing. The UI stream handler and parser are responsible here.


## Troubleshooting guide

- Symptom: One word per line (“poem mode”).
- Cause: Client added \n after every event (was appending data + "\n").
Fix: Append data as‑is; newlines are already preserved in multi‑line data: events.

- Symptom: Words stuck together (ChooseAforspeed...).
- Cause: The parser did .lstrip() on data: content, erasing spaces that are part of tokens.
- Fix: Trim only one leading space after data: as per spec.

- Symptom: Markdown looks like plain text.
- Cause: Newlines lost in transit (see two issues above) or HTML unsafe mode confusion.
- Fix: Ensure Gateway emits multi‑line data: events, client doesn’t inject newlines, and keep unsafe_allow_html=false (we rely on Markdown renderer, not raw HTML).

## Performance & compatibility

- TTFT/TPOT unchanged. We only changed framing of SSE events and a small client parser; the chunk count and I/O are effectively the same. The overall streaming architecture remains as documented in our infra notes.

- Backwards‑compatible: UI can consume standard SSE; Gateway emits spec‑compliant SSE. The feature is local to these two components.

## Summary: 

#### This feature makes our streaming path SSE‑spec compliant and Markdown‑faithful. The Gateway emits newline‑preserving events; the UI parses them precisely and lets Chainlit do the Markdown → HTML rendering, with CSS polish and no security trade‑offs.

