---
name: memory-write
description: Persist decisions, findings, experiment results, and architecture knowledge into Codebuff's memory system so future sessions benefit from accumulated experience. Use after completing a significant task, diagnosing a bug, making an architectural decision, or running an experiment. Creates structured records in .qoder/memory/.
---

# Memory Write

Persist what you learned so future Codebuff sessions don't start from zero.

## Why This Exists

Codebuff has no persistent memory. Every lesson learned disappears when the session ends. Memory-Write is how the system improves over time: each session builds on the accumulated knowledge of all previous sessions.

## What to Write

Write memory entries for these events:

| Event | Category | Example |
|-------|----------|---------|
| Architectural decision | `decisions/` | "Chose Dhan as primary broker because Upstox has 2-min historical data TTL" |
| Bug found and fixed | `findings/` | "Partial fill race condition: cancel() returns success but order fills before cancel hits exchange" |
| Experiment completed | `experiments/` | "Tested moving Upstox historical from V2 to V3 API — 40% faster but missing expired options" |
| Architecture map update | `architecture/` | "Added new seam between OMS and PositionManager" |
| Integration pattern discovered | `findings/` | "Both Dhan and Upstox need same correlation ID pattern — extract to common" |

## Process

### 1. Classify the Event

Determine which category the knowledge belongs to:

- **decisions/**: Things you chose consciously with alternatives
- **findings/**: Things you discovered through investigation
- **experiments/**: Things you tested with measurable outcomes
- **architecture/**: Things about module structure, seams, and boundaries

### 2. Format the Entry

Use this template based on category:

#### Decision Template
```markdown
# [Decision Title]

**Date**: [YYYY-MM-DD]
**Context**: [What prompted this decision]
**Alternatives Considered**: [What else was evaluated]
**Decision**: [What was chosen]
**Rationale**: [Why this choice over alternatives]
**Consequences**: [What this means going forward]
**Relevant Modules**: [module1.py, module2.py]
```

#### Finding Template
```markdown
# [Finding Title]

**Date**: [YYYY-MM-DD]
**Discovered During**: [What task revealed this]
**Symptom**: [What was observed]
**Root Cause**: [What was actually wrong]
**Fix Applied**: [What change fixed it]
**Prevention**: [How to avoid in the future]
**Related Tests**: [test_file1.py, test_file2.py]
```

#### Experiment Template
```markdown
# [Experiment Title]

**Date**: [YYYY-MM-DD]
**Hypothesis**: [What we expected to happen]
**Method**: [How we tested it]
**Metric**: [What we measured and how]
**Result**: [What actually happened, with numbers]
**Conclusion**: [What we learned]
**Next Steps**: [What to try next or what this unblocks]
```

#### Architecture Template
```markdown
# [Architecture Update]

**Date**: [YYYY-MM-DD]
**Module(s) Affected**: [module paths]
**Change**: [What changed structurally]
**Motivation**: [Why the change was needed]
**Seams Involved**: [Ports/adapters affected]
**Migration Status**: [In progress | Complete | Planned]
```

### 3. Write the File

Create the file at:
```
.qoder/memory/<category>/<YYYY-MM-DD>-<kebab-case-title>.md
```

Example: `.qoder/memory/decisions/2026-07-02-primary-broker-selection.md`

### 4. Update Knowledge Index

If this is significant knowledge, also update the relevant section in `.qoder/repowiki/` if it exists. This keeps the human-readable documentation in sync with the agent-readable memory.

## Auto-Trigger Rules

Write memory automatically after:

| Trigger | Action |
|---------|--------|
| Bug fixed | Write finding with root cause and prevention |
| ADR created or updated | Write decision with rationale |
| Architecture changed | Write architecture update |
| Refactoring completed | Write architecture update with seam changes |
| Experiment completed | Write experiment with metric and outcome |
| Integration pattern discovered | Write finding |
| User says "remember this" | Write whatever follows as a finding |

## Constraints

- NEVER write duplicate entries — check if similar memory already exists
- NEVER write ephemeral details (temp variables, debug prints, intermediate states)
- NEVER write sensitive information (API keys, credentials, personal data)
- ALWAYS include the date for chronological ordering
- ALWAYS link to specific files/modules for actionability
- Keep entries concise — one topic per file
