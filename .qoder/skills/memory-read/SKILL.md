---
name: memory-read
description: Query Codebuff's persistent agent memory to recall past decisions, bug patterns, architectural findings, and experiments. Use before starting any significant task to avoid repeating past mistakes and to leverage accumulated knowledge. Auto-triggered when loading a project with existing .qoder/memory/ directory.
---

# Memory Read

Query persistent agent memory for relevant context before acting.

## Why This Exists

Codebuff has no persistent memory by default. Every session starts from scratch. The memory system bridges this gap: decisions, bug patterns, and architectural findings survive across sessions so the system improves over time.

## Process

### 1. Scan Available Memory

Check what memory categories exist in `.qoder/memory/`:

```
.qoder/memory/
├── decisions/      — ADR-style decision records
├── findings/       — Bug patterns, diagnosis insights
├── experiments/    — Git-based experiment logs
└── architecture/   — Living architecture map (module deps, seams, migrations)
```

List the files in each category to understand what's available.

### 2. Query by Relevance

Search memory files using grep for keywords related to the current task:

```
grep -ri "<keyword>" .qoder/memory/ --include="*.md"
```

Keywords to try:
- Module names (e.g., "dhan", "upstox", "broker")
- Problem patterns (e.g., "race condition", "partial fill", "rate limit")
- Architecture terms (e.g., "seam", "port", "adapter", "bounded context")
- Decision types (e.g., "ADR", "architecture decision", "rejected")

### 3. Synthesize Findings

From matched results, extract:

```markdown
## Memory Summary: [Task]

### Relevant Past Decisions
- [Decision 1] — [file:line] — [summary]
- [Decision 2] — [file:line] — [summary]

### Relevant Bug Patterns
- [Bug 1] — [file] — [symptoms + fix]
- [Bug 2] — [file] — [symptoms + fix]

### Relevant Experiments
- [Experiment 1] — [hypothesis → result]

### Key Constraints
- [Constraint 1: e.g., "Don't use float for prices"]
- [Constraint 2: e.g., "Paper broker must match live broker interface"]
```

### 4. Flag Gaps

If a relevant topic has NO memory entries, flag it:

> ⚠️ No memory entries found for [topic]. Consider running `/memory-write` after completing this task to capture what you learn.

## Output Format

Respond with this structure when memory is found:

```markdown
🧠 Memory Found: [count] entries relevant to [task]

### Key Findings
- [Most important finding]

### Full Context
[Summarized relevant entries]

### Suggested Action
- [Should this change approach based on past decisions?]
- [Should previous experiment be retried with new understanding?]
```

Respond with this structure when no memory is found:

```markdown
🧠 No Relevant Memory Found

This appears to be a new area. After completing this task, consider running `/memory-write` to capture what you learn for future sessions.
```

## Auto-Trigger Rules

Load memory automatically when:

| Trigger | Action |
|---------|--------|
| User says "improve X" | Query memory for past improvement attempts on X |
| User says "fix bug in X" | Query memory for bug patterns in X |
| User says "add feature X" | Query memory for architectural decisions near X |
| User says "refactor X" | Query memory for past refactoring attempts on X |
| Starting any task > 100 lines | Query memory for relevant context |
| Diagnosing a bug | Query memory for similar past bugs |
| New project with `.qoder/memory/` | Auto-load on session start |

## Constraints

- NEVER modify memory files during a read operation
- NEVER skip the memory read for tasks that modify production code
- If memory is empty, note it and proceed — don't block
- If memory contradicts the current approach, flag it and ask the user
