# Agent Harness — Design Bundle

Everything produced for the multi-tenant agent harness design, current as of the latest revision.

## Contents

```
agent-harness-design/
├── agent-harness-system-design.md   ← the design doc (v0.4) — start here
├── diagrams/
│   ├── png/   6 diagrams, 4× high-resolution raster
│   ├── svg/   6 diagrams, vector (infinite scale)
│   └── src/   6 diagrams, editable Mermaid source (.mmd)
└── mockups/
    ├── platform-console.html / .png   platform-owner dashboard
    └── tenant-console.html   / .png   per-tenant dashboard
```

## The design doc

`agent-harness-system-design.md` is the single source of truth. It embeds the same
six diagrams as inline Mermaid (renders in any Mermaid-aware viewer, e.g. GitHub,
Obsidian, VS Code). The files in `diagrams/` are standalone exports of those same
diagrams for dropping into slides, docs, or a wiki.

## The six diagrams

1. **01-high-level-architecture** — full system, layer by layer.
2. **02-handover-sequence** — transparent agent-to-agent handover in a shared thread.
3. **03-trading-risk-gate** — bounded-autonomous trading (envelope + circuit breakers).
4. **04-deployment-topology** — Docker/VPS process and datastore layout.
5. **05-control-plane** — two planes (platform + tenant) over one RBAC'd API.
6. **06-worker-lifecycle** — what one worker does from dequeue to delivery.

To re-render or edit a diagram: open the matching `.mmd` in `diagrams/src/`, or paste
it into https://mermaid.live. PNGs/SVGs here were generated with `@mermaid-js/mermaid-cli`.

## The mockups

Static, self-contained HTML (no external dependencies) — open the `.html` files in any
browser. The `.png` versions are 2× screenshots for quick reference. The approval inbox
is intentionally absent from both: approvals happen in the chat thread; the dashboards
show only a pending count.

## Status

Design only — no implementation. All open decisions are resolved in §15 of the doc.
Remaining to set: the trading agent's envelope numbers (caps, daily-loss limit,
confidence floor), to be chosen conservatively and proven in paper mode before going live.
