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

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Split on blank lines — each chunk is one SSE event.
    let separator = buffer.indexOf("\n\n");
    while (separator !== -1) {
      const rawEvent = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);

      let eventName = "message";
      const dataLines: string[] = [];
      for (const line of rawEvent.split("\n")) {
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
      separator = buffer.indexOf("\n\n");
    }
  }
}
