# Documentation Index

Everything written down about AutoOverlay AI. Start here.

| Document | What it covers |
|---|---|
| [`../README.md`](../README.md) | Project overview, quickstart, repo layout |
| [`JOBDESK.md`](JOBDESK.md) | Who owns what, per-role scope boundaries, handoff rules |
| [`AI-ENGINEER.md`](AI-ENGINEER.md) | The agent layer in depth: strategies, decision engine, exits, orchestration |
| [`HEDGE-FUND-COUNCIL.md`](HEDGE-FUND-COUNCIL.md) | Investment Council: 6 personas, Graham-from-the-book, Mr. Market, dissent |
| [`FRONTEND.md`](FRONTEND.md) | Next.js layer: API client, layout, brand, charts, motion |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System diagram, data flow, module responsibilities |
| [`API-CONTRACT.md`](API-CONTRACT.md) | Every endpoint with its **actual verified** response shape |
| [`RISK-MANAGEMENT.md`](RISK-MANAGEMENT.md) | Kill-switch, caps, exit rules, tier policy, and what each is for |
| [`MEMORY.md`](MEMORY.md) | Dated build log from zero to now, with criticism per milestone |
| [`TESTING.md`](TESTING.md) | Test suite map, what is covered, what is **not** |
| [`security_review.md`](security_review.md) | Penetration test findings and fixes |
| [`council_report.md`](council_report.md) | Live council output on the 8-symbol universe |
| [`KNOWN-ISSUES.md`](KNOWN-ISSUES.md) | Open defects, contract mismatches, unfinished work |
| [`ROADMAP.md`](ROADMAP.md) | What is next, ordered by value |

## Reading order for a newcomer

1. `../README.md` — what this thing is
2. `ARCHITECTURE.md` — how the pieces fit
3. `RISK-MANAGEMENT.md` — the part that matters most in a trading system
4. `AI-ENGINEER.md`, `HEDGE-FUND-COUNCIL.md`, or `FRONTEND.md` — depending on which layer you touch
5. `KNOWN-ISSUES.md` — before you assume something is broken by your change

## Honesty policy for these documents

These docs describe **what the code actually does**, verified by reading it and
running it — not what was planned. Where a claim could not be verified, it says
so. Where a document contradicts the code, the code wins and the document is a
bug. If you change behaviour, update the doc in the same commit.
