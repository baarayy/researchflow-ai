// Minimal Server-Sent Events parser over fetch(). Unlike EventSource it lets us send headers
// (Last-Event-ID on reconnect) and abort cleanly.

export interface SseMessage {
  id?: string;
  event: string;
  data: string;
}

export function parseSseChunk(buffer: string): { messages: SseMessage[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const blocks = normalized.split("\n\n");
  const rest = blocks.pop() ?? "";
  const messages: SseMessage[] = [];
  for (const block of blocks) {
    const msg: SseMessage = { event: "message", data: "" };
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue; // comment / keep-alive ping
      const idx = line.indexOf(":");
      const field = idx === -1 ? line : line.slice(0, idx);
      const value = idx === -1 ? "" : line.slice(idx + 1).replace(/^ /, "");
      if (field === "event") msg.event = value;
      else if (field === "data") data.push(value);
      else if (field === "id") msg.id = value;
    }
    if (data.length || msg.id) {
      msg.data = data.join("\n");
      messages.push(msg);
    }
  }
  return { messages, rest };
}

export async function readSse(
  url: string,
  { lastEventId, signal, onMessage }: { lastEventId?: string; signal: AbortSignal; onMessage: (m: SseMessage) => void },
): Promise<void> {
  const response = await fetch(url, {
    headers: { Accept: "text/event-stream", ...(lastEventId ? { "Last-Event-ID": lastEventId } : {}) },
    signal,
  });
  if (!response.ok || !response.body) throw new Error(`Event stream failed (${response.status})`);
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    const { messages, rest } = parseSseChunk(buffer + value);
    buffer = rest;
    messages.forEach(onMessage);
  }
}
