import { describe, expect, it } from "vitest";

import { parseSseChunk } from "@/lib/sse";

describe("parseSseChunk", () => {
  it("parses complete messages and keeps the partial remainder", () => {
    const { messages, rest } = parseSseChunk(
      'id: 7\r\nevent: node\r\ndata: {"a":1}\r\n\r\n: ping\r\n\r\nevent: end\r\ndata: {}\r\n\r\nid: 8\r\nevent: no',
    );
    expect(messages).toEqual([
      { id: "7", event: "node", data: '{"a":1}' },
      { event: "end", data: "{}" },
    ]);
    expect(rest).toBe("id: 8\nevent: no");
  });

  it("joins multi-line data", () => {
    expect(parseSseChunk("data: a\ndata: b\n\n").messages[0].data).toBe("a\nb");
  });
});
