# Decision: repo-graph MCP Server for Codebase Graph Integration

**Date**: 2026-07-02
**Context**: The Karpathy-inspired agent system needs a structural map of the codebase for blast radius analysis, dependency tracing, and change impact assessment. Without a codebase graph, agents must rely on grep (which has false positives from comments/strings) and manual reasoning.
**Alternatives Considered**:
- **Grep-only**: No setup needed, but fragile — matches comments, strings, and variable names. No cross-language awareness. No entity-level resolution.
- **AST parsers (tree-sitter directly)**: More precise than grep but requires per-language setup per agent. No MCP integration for tooling.
- **repo-graph MCP server**: Uses tree-sitter internally, exposes 13 MCP tools (status, trace, flow, impact, activate, find, dense_text, etc.), generates a 26MB graph cache locally, and integrates as a stdio MCP server. Cross-stack awareness (TypeScript ↔ Python).

**Decision**: Deploy repo-graph MCP server (`mcp-repo-graph` via `uvx`) with three integration points.

**Rationale**:
1. repo-graph provides entity-level resolution via tree-sitter (no grep false positives)
2. MCP protocol means any tool can call `status`, `activate`, `trace`, `impact`, etc.
3. Cross-stack edges (77 found) connect frontend HTTP calls to backend routes
4. Graph cache (26MB, 9,429 nodes, 15,602 edges) enables fast analysis without re-parsing
5. Local-only — no code or graph data sent to external servers

**Consequences**:
- Agents should use repo-graph tools (`activate`, `trace`, `impact`) instead of grep for structural queries
- `.ai/repo-graph/` must be kept in sync with the codebase (pre-commit hook + CI enforce this)
- `.codebuff → .qoder` symlink created for naming clarity
- Pre-commit hook ensures graph cache is refreshed before every commit
- CI workflow validates graph integrity on every PR

**Integration Points**:
1. **MCP server** (`.mcp.json`): stdio server running `mcp-repo-graph --repo .`
2. **Pre-commit hook** (`.git/hooks/pre-commit`): runs `repo-graph-init` before every commit, stages cache updates
3. **CI workflow** (`.github/workflows/repo-graph-validate.yml`): validates graph generation + drift detection on every PR

**Relevant Modules**:
- .mcp.json
- .git/hooks/pre-commit
- .github/workflows/repo-graph-validate.yml
- .qoder/agents/codebase-cartographer.md
- .qoder/skills/blast-radius/SKILL.md
- .ai/repo-graph/manifest.json
- CLAUDE.md
