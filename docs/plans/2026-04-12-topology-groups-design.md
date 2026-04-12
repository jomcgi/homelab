# Topology Groups (Buckets) Design

## Problem

The observability demo renders all services as flat peer nodes. This doesn't capture:

- Sub-services within the monolith (home, knowledge, chat)
- MCP server types hosted inside Context Forge

## Solution

Add hierarchical groups to the topology. A group is a visual boundary (rough.js rectangle) containing child nodes.

## Groups

**MONOLITH** (critical, ingress) — children: HOME, KNOWLEDGE, CHAT
**CONTEXT FORGE** (critical, ingress) — children: K8S, ARGOCD, SIGNOZ

## New Node

**DISCORD** — external-tier node representing the Discord API

## Data Model

New `groups` array in `topology.json`:

```json
{
  "groups": [
    {
      "id": "monolith",
      "label": "MONOLITH",
      "children": ["home", "knowledge", "chat"],
      ...metrics
    },
    {
      "id": "context-forge",
      "label": "CONTEXT FORGE",
      "children": ["k8s-mcp", "argocd-mcp", "signoz-mcp"],
      ...metrics
    }
  ]
}
```

Children are full nodes in the `nodes` array. Edges reference child IDs directly.

## Edge Map

- cloudflare → home
- cloudflare → knowledge
- cloudflare → agent-platform
- home → postgres
- knowledge → postgres
- knowledge → voyage-embedder
- knowledge → llama-cpp (gemma 4)
- chat → llama-cpp (gemma 4)
- chat → discord
- nats ↔ agent-platform
- agent-platform → context-forge (group boundary)
- context-forge internal: k8s, argocd, signoz (MCP servers)

## Layout

Dagre compound graphs via `g.setParent(childId, groupId)`. Group nodes get extra padding so dagre leaves room for the boundary. Children positioned inside automatically.

## Rendering

- **Group boundary:** Rough.js rectangle around children's bounding box + padding
- **Group label:** Top-left corner, smaller/lighter weight
- **Tier fill:** Same tier color at ~30% opacity (subtle wash)
- **Child nodes:** Full rough.js rectangles as today

## Animation Sequence

1. BFS proceeds normally — child nodes draw individually (pencil → ink → fill → text)
2. Edges pierce through group boundary to connect directly to children
3. After ALL children in a group complete their ink phase, group boundary animates:
   - Pencil sketch of boundary (sequential sides)
   - Ink retrace follows
   - Group label jots in
   - Subtle fill wash fades in

## Detail Drawer

- Click group boundary → aggregate group metrics
- Click child → child metrics with "part of: GROUP" breadcrumb

## Label Simplification

MCP server children use short labels (K8S, ARGOCD, SIGNOZ) since the group label provides context.
