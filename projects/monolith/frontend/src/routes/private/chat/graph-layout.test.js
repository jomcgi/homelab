import { describe, it, expect } from "vitest";
import { createGraphState } from "./graph-layout.js";

describe("createGraphState", () => {
  it("starts empty", () => {
    const gs = createGraphState();
    const result = gs.layout();
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("adds a node and assigns position after layout", () => {
    const gs = createGraphState();
    const added = gs.addNode({
      note_id: "n1",
      title: "Kubernetes",
      type: "note",
      tags: ["k8s"],
      snippet: "Overview",
      edges: [],
    });

    expect(added).toBe(true);
    expect(gs.getNodeCount()).toBe(1);

    const result = gs.layout();
    expect(result.nodes).toHaveLength(1);
    expect(result.nodes[0].id).toBe("n1");
    expect(result.nodes[0].x).toBeTypeOf("number");
    expect(result.nodes[0].y).toBeTypeOf("number");
    expect(result.nodes[0].isNew).toBe(true);
  });

  it("deduplicates nodes", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    const second = gs.addNode({ note_id: "n1", title: "A", type: "note" });

    expect(second).toBe(false);
    expect(gs.getNodeCount()).toBe(1);
  });

  it("adds edges between nodes", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    gs.addNode({ note_id: "n2", title: "B", type: "article" });
    const added = gs.addEdge("n1", "n2", "related");

    expect(added).toBe(true);

    const result = gs.layout();
    expect(result.edges).toHaveLength(1);
    expect(result.edges[0]).toEqual({ from: "n1", to: "n2", type: "related" });
  });

  it("deduplicates edges", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    gs.addNode({ note_id: "n2", title: "B", type: "article" });
    gs.addEdge("n1", "n2", "related");
    const second = gs.addEdge("n1", "n2", "related");

    expect(second).toBe(false);
  });

  it("tracks previous positions for smooth transitions", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    const first = gs.layout();

    // Add a second node — dagre will reposition n1
    gs.addNode({ note_id: "n2", title: "B", type: "article" });
    gs.addEdge("n1", "n2", "link");
    const second = gs.layout();

    const n1 = second.nodes.find((n) => n.id === "n1");
    // n1 existed before, so it should have prev positions
    expect(n1.isNew).toBe(false);
    expect(n1.prevX).toBe(first.nodes[0].x);
    expect(n1.prevY).toBe(first.nodes[0].y);

    // n2 is new — no prev positions
    const n2 = second.nodes.find((n) => n.id === "n2");
    expect(n2.isNew).toBe(true);
    expect(n2.prevX).toBeUndefined();
  });

  it("marks discarded nodes", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    gs.discardNode("n1");

    const result = gs.layout();
    expect(result.nodes[0].discarded).toBe(true);
  });

  it("discarding unknown node is a no-op", () => {
    const gs = createGraphState();
    gs.discardNode("nonexistent"); // should not throw
    expect(gs.getNodeCount()).toBe(0);
  });

  it("reset clears all state", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "n1", title: "A", type: "note" });
    gs.addNode({ note_id: "n2", title: "B", type: "article" });
    gs.addEdge("n1", "n2", "link");

    gs.reset();

    expect(gs.getNodeCount()).toBe(0);
    const result = gs.layout();
    expect(result.nodes).toEqual([]);
    expect(result.edges).toEqual([]);
  });

  it("computes hw proportional to label length", () => {
    const gs = createGraphState();
    gs.addNode({ note_id: "short", title: "Hi", type: "note" });
    gs.addNode({
      note_id: "long",
      title: "A Very Long Title For Testing",
      type: "note",
    });

    const result = gs.layout();
    const short = result.nodes.find((n) => n.id === "short");
    const long = result.nodes.find((n) => n.id === "long");
    expect(long.hw).toBeGreaterThan(short.hw);
  });

  it("handles full exploration sequence matching backend events", () => {
    const gs = createGraphState();

    // Simulate the SSE event sequence from the backend integration test:
    // 1. search_kg discovers note-1
    gs.addNode({
      note_id: "note-1",
      title: "Kubernetes Networking",
      type: "note",
      tags: ["k8s", "networking"],
      snippet: "Service mesh overview...",
      edges: [{ target_id: "note-2", edge_type: "refines" }],
    });

    // 2. expand_node traverses edge and discovers note-2
    gs.addEdge("note-1", "note-2", "related");
    gs.addNode({
      note_id: "note-2",
      title: "Linkerd",
      type: "article",
      tags: ["service-mesh"],
    });

    // 3. discard_node marks note-2 as irrelevant
    gs.discardNode("note-2");

    const result = gs.layout();

    // Both nodes positioned
    expect(result.nodes).toHaveLength(2);
    expect(result.nodes.every((n) => typeof n.x === "number")).toBe(true);

    // Edge connects them
    expect(result.edges).toHaveLength(1);
    expect(result.edges[0].from).toBe("note-1");
    expect(result.edges[0].to).toBe("note-2");

    // note-2 is discarded
    const note2 = result.nodes.find((n) => n.id === "note-2");
    expect(note2.discarded).toBe(true);

    // note-1 is not discarded
    const note1 = result.nodes.find((n) => n.id === "note-1");
    expect(note1.discarded).toBe(false);
  });
});
