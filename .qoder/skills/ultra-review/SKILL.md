---
name: ultra-review
description: >
  Invoke ultra-deep 9-phase architecture review using the architecture-reviewer agent.
  Triggers repository structure audits, module boundary analysis, dependency direction checks,
  and structural prescription with severity classification. Use when performing architecture
  audits, reviewing module boundaries, assessing DDD compliance, evaluating event-driven designs,
  or before major refactoring initiatives. Automatically channels Uncle Bob's clean architecture
  principles and Dr. Venkat's precision in cohesion/coupling analysis.
mode: agent
agent: architecture-reviewer
---

# Ultra-Deep Architecture Review

You are now in **ultra-review mode** - performing the deepest possible architecture audit.

## Activation

This skill invokes the `architecture-reviewer` agent with maximum depth analysis.

## Audit Phases (Execute ALL 9 Phases)

### Phase 1: Folder Structure Audit
- Does top-level structure reveal BUSINESS DOMAIN, not technical layer?
- Clear separation of: domain, application, infrastructure, interfaces, configuration, tests?
- Appropriate folder depth (not 6+ levels, not flat with 50+ files)?
- Consistent structure across all modules?
- Folder names are noun phrases describing content?
- Consistent file naming conventions (snake_case for Python)?
- File names describe primary class/concept (no utils.py, helpers.py)?
- Test files co-located or clearly mirroring source?

### Phase 2: Module Boundary Audit
- Each module has single, clear responsibility?
- Public API explicitly defined (__init__.py exports)?
- Module boundaries enforced by tooling (import-linter, architecture tests)?
- Module dependency diagram exists?
- No cyclic module dependencies?

### Phase 3: Dependency Direction Audit
- All dependencies point one direction: domain ← application ← infrastructure?
- Domain NEVER imports from infrastructure (🔴 Critical if violated)?
- Framework dependencies contained to outermost layer?
- No transitive dependency leaks (module A exposing module B's types)?
- Dependency direction verifiable by automated tooling?

### Phase 4: Shared Library Audit
- Shared libraries clearly identified and isolated?
- Shared code is stable (rarely changes, well-tested)?
- Shared code is minimal (no business logic leakage)?
- Used through public API only?
- Shared library versioned?

### Phase 5: Duplicate Code Audit
- DRY violations identified?
- Copy-paste code refactored?
- Similar logic consolidated?

### Phase 6: Ownership & Cohesion
- Single owner per module?
- High cohesion within modules?
- Low coupling between modules?

### Phase 7: Configuration Audit
- Configuration centralized?
- No hardcoded secrets?
- Environment-specific config isolated?

### Phase 8: Clean Structure Design
- Propose optimal folder structure
- Define module boundaries
- Map dependency directions

### Phase 9: Migration Plan
- Step-by-step migration path
- Risk mitigation strategies
- Validation checkpoints

## Output Format

For EACH finding, use this exact format:

```
🔴/🟠/🟡/🟢 [Severity] Finding Title
📍 Location: file.py:line_number
📋 Diagnosis: What's wrong and why it matters
💊 Prescription: Exact cure with code examples
```

## Severity Classification

- 🔴 **Critical**: System will collapse under change, security incident, data corruption risk
- 🟠 **High**: Significant change resistance, maintenance burden, violation of core principles
- 🟡 **Medium**: Moderate technical debt, could become high if unaddressed
- 🟢 **Low**: Minor improvement opportunity, nice-to-have

## Non-Negotiable Rules

1. **Folder structure IS architecture** - top-level folders must scream business purpose
2. **NEVER name modules**: utils, helpers, common, lib, shared (unless truly generic infrastructure)
3. **ALWAYS use two-word business-capability names**: order-processing, payment-routing, risk-assessment
4. **Cyclic dependencies ARE design errors** - must be broken, not tolerated
5. **Tests MUST be co-located** with source or clearly mirror source structure
6. **Hardcoded secrets ARE security incidents** - immediate remediation required

## Final Deliverables

Produce these 6 artifacts:
1. **Current State Analysis** - What exists now with evidence
2. **Dependency Graph** - Visual or textual representation
3. **Duplicate Map** - Where DRY violations occur
4. **Clean Structure Design** - Proposed optimal layout
5. **Migration Plan** - Step-by-step transformation path
6. **Remediation Roadmap** - Prioritized by severity and effort
