// Minimal SSE-over-POST parser. The browser's native EventSource only supports
// GET, but /api/score is a multipart POST that streams sse-starlette events
// back. So we hand-roll a ReadableStream consumer that yields {event, data}.
//
// Spec recap (only the bits we use): events are separated by blank lines;
// each event has zero or more `event:`/`data:`/`id:`/`retry:` lines.

export type SSEEvent = { event: string; data: string };

export async function* streamSSE(
  url: string,
  init: RequestInit,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent, void, unknown> {
  const response = await fetch(url, { ...init, signal });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 300)}`);
  }
  if (!response.body) {
    throw new Error("SSE response had no body");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  // Find the next blank-line separator: prefer LF/LF, fall back to CRLF/CRLF.
  // Some proxies (Cloudflare, NGINX) normalize line endings; the SSE spec
  // permits either, so handle both.
  const nextSeparator = (s: string): { idx: number; len: number } => {
    const lf = s.indexOf("\n\n");
    const crlf = s.indexOf("\r\n\r\n");
    if (lf === -1 && crlf === -1) return { idx: -1, len: 0 };
    if (lf === -1) return { idx: crlf, len: 4 };
    if (crlf === -1) return { idx: lf, len: 2 };
    return lf < crlf ? { idx: lf, len: 2 } : { idx: crlf, len: 4 };
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep = nextSeparator(buffer);
    while (sep.idx !== -1) {
      const rawEvent = buffer.slice(0, sep.idx);
      buffer = buffer.slice(sep.idx + sep.len);

      let eventName = "message";
      const dataLines: string[] = [];
      // Split on either LF or CRLF — within an event, lines can be separated
      // by either too.
      for (const line of rawEvent.split(/\r?\n/)) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trim());
        }
        // ignore id:, retry:, comments (lines starting with ":")
      }
      if (dataLines.length > 0) {
        yield { event: eventName, data: dataLines.join("\n") };
      }
      sep = nextSeparator(buffer);
    }
  }
}
