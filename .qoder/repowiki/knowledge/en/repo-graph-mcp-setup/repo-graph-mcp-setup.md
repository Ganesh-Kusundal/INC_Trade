# repo-graph MCP Server Setup

The project uses [repo-graph](https://github.com/James-Chahwan/repo-graph) — an MCP server that generates a structural codebase graph using tree-sitter. It exposes 13 tools for entity-level code navigation, dependency tracing, and blast radius analysis.

## Status: ✅ Active (2026-07-02)

## Graph Stats

| Metric | Value |
|--------|-------|
| Files parsed | 567 |
| Nodes | 9,429 |
| Edges | 15,602 |
| Cross-stack edges | 77 |
| Cache size | 26 MB |
| Engine | `repo-graph-py 0.4.16` |

## Integration Points

### 1. MCP Server (`.mcp.json`)

The server runs as a stdio MCP process via `uvx`:

```json
{
  "mcpServers": {
    "repo-graph": {
      "type": "stdio",
      "command": "repo-graph",
      "args": ["--repo", "/path/to/repo"]
    }
  }
}
```

The graph cache lives at `.ai/repo-graph/` and is automatically generated on first connection.

### 2. Pre-Commit Hook (`.git/hooks/pre-commit`)

A git pre-commit hook runs `uvx --from mcp-repo-graph repo-graph-init --repo .` before every commit. This ensures the graph cache stays fresh and is staged alongside code changes.

- **Non-blocking**: If `uvx` is unavailable, the hook prints a warning and lets the commit proceed.
- **Auto-staging**: If the graph cache updates during the hook, it's automatically staged.

### 3. CI Workflow (`.github/workflows/repo-graph-validate.yml`)

A GitHub Actions workflow validates the graph on every PR:

| Step | Purpose |
|------|---------|
| **Checkout** | Clone the repo |
| **Install uv** | Via `astral-sh/setup-uv` (pinned to commit SHA) |
| **Restore cache** | Cache key covers `**/*.py`, `requirements.txt`, `pyproject.toml` |
| **Snapshot** | Save committed `.ai/repo-graph/` before regeneration (enables drift detection) |
| **Generate & Validate** | Run `repo-graph-init`, verify `manifest.json` + segment files exist |
| **Drift Check** | Diff fresh generation against committed snapshot — fails the build if they differ |
| **Summary** | Report results to `$GITHUB_STEP_SUMMARY` |

Triggers: PRs to `main`/`master`/`develop`, pushes to `main`/`master`.

### 4. Agent System Integration

Two agents in the Karpathy system were updated to use repo-graph:

- **`codebase-cartographer`** — Now uses repo-graph tools (`status` → `dense_text` → `activate` → `flow/trace` → `find`) as its primary analysis method, with grep as fallback.
- **`blast-radius` skill** — Phase 0 loads repo-graph for entity-level dependency resolution before falling back to grep.

## repo-graph MCP Tools

| Tier | Tool | Purpose |
|------|------|---------|
| **Generation** | `generate` | Scans code with tree-sitter, builds/updates graph cache |
| **Navigation** | `status` | High-level codebase overview |
| | `flow` | End-to-end feature trace (JWT → API → service → DB) |
| | `trace` | Shortest path between two modules |
| | `impact` | Blast radius for a symbol |
| | `neighbours` | Immediate dependency neighbors |
| | `read` | Fetch exact source code lines |
| **Activation** | `activate` | Find relevant nodes from seed terms (spreading activation) |
| | `find` | Search by entity name/pattern |
| | `locate` | Resolve errors/diffs to code |
| | `dense_text` | Full structural context for a set of nodes |
| **Health** | `graph_view` | ASCII graph visualization |
| | `reload` | Force graph reload |

## Developer Notes

- **Manual refresh**: `uvx --from mcp-repo-graph repo-graph-init --repo .`
- **Cache location**: `.ai/repo-graph/` (not gitignored — committed for fast CI cache hits)
- **Language support**: Python, TypeScript, Go, Rust, Java, C#, and many more
- **Privacy**: Local-only — no code or graph data is sent to external servers
- **Memory**: A decision record was written to `.qoder/memory/decisions/2026-07-02-repo-graph-mcp-setup.md`
