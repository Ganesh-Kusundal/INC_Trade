# Master Remediation & Execution Plan — Brokers Adapter Package

This document establishes the **Phase 0 Execution Plan** to address the 12 compliance and structural issues identified inside the `brokers/` package, adhering to the rules in [execution-planning](file:///Users/apple/Downloads/INC_Trade/.qoder/skills/execution-planning/SKILL.md) and [ultra-plan](file:///Users/apple/Downloads/INC_Trade/.qoder/skills/ultra-plan/SKILL.md).

---

## 1. Compiled Findings Inventory

### Phase A: Critical / Immediate (Runtime Safety & Type Gates)
| ID | Finding | Location | Severity | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **A1** | Import NameError in capabilities | `brokers/paper/paper_gateway.py:429` | 🔴 Critical | Runtime crash / undefined symbol |
| **A2** | OAuth return type mismatch | `brokers/upstox/auth/token_manager.py:280` | 🔴 Critical | Dynamic type runtime crash |
| **A3** | Built-in lowercase `any` type hint | `brokers/upstox/auth/token_manager.py:53` | 🔴 Critical | Attribute resolution type failure |

### Phase B: Structural (LSP, Encapsulation, & Normalization)
| ID | Finding | Location | Severity | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **B1** | LSP `history` signature mismatch | `brokers/dhan/gateway.py:468` & `brokers/upstox/gateway.py:255` | 🟠 High | Interface contract violation |
| **B2** | LSP return status mismatch | `brokers/dhan/gateway.py:659` | 🟠 High | Interface contract violation |
| **B3** | Connection Factory Monkey-Patching | `brokers/dhan/factory.py:315` | 🟠 High | Encapsulation bypass / hidden state |
| **B4** | Builder Inappropriate Intimacy | `brokers/upstox/broker.py:194` | 🟠 High | Tight coupling / warnings |
| **B5** | Unnormalized adapter exceptions | `brokers/dhan/gateway.py:130` (Exception catches) | 🟠 High | Provider exception leakage |

### Phase C: Hardening (Feature Completeness & Optimization)
| ID | Finding | Location | Severity | Risk |
| :--- | :--- | :--- | :--- | :--- |
| **C1** | Missing Upstox adapter portfolio methods | `brokers/upstox/gateway.py` | 🟠 High | Feature block / missing API |
| **C2** | Speculative async client dead code | `brokers/dhan/async_http_client.py` | 🟡 Medium | Unused code bloat (YAGNI) |
| **C3** | Options dictionary primitive obsession | `brokers/dhan/options.py:233` | 🟡 Medium | Inferred type warnings |
| **C4** | Missing WS ping/heartbeat listeners | `brokers/dhan/reconnecting_service.py` | 🟡 Medium | Ghost connection price loss |

---

## 2. Dependency Graph

```
[A1: Paper NameError] ──┐
[A2: Upstox OAuth]    ──┼─> [B1/B2: LSP Signatures] ──> [C1: Upstox Methods] ──> [C4: WS Heartbeat]
[A3: Upstox 'any' hint] ─┘          │                                            ^
                                    v                                            │
                             [B3/B4: Inject/Builder] ────────────────────────────┘
```

---

## 3. Parallel Execution Matrix (Queues A/B/C/D)

We classify the remediation items into execution queues to maximize concurrency while protecting critical paths:

| Task ID | Description | Queue | Can Run in Parallel With | Prerequisite | Owner (Agent) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A1** | Fix Paper capabilities imports | **Queue A** | A2, A3 | None | `deep-static-auditor` |
| **A2** | Fix Upstox OAuth return types | **Queue A** | A1, A3 | None | `deep-static-auditor` |
| **A3** | Replace built-in `any` type hint | **Queue A** | A1, A2 | None | `deep-static-auditor` |
| **B1** | Align `history()` parameters | **Queue B** | B2, B3, B4 | Queue A complete | `architecture-reviewer` |
| **B2** | Align `get_connection_status()` | **Queue B** | B1, B3, B4 | Queue A complete | `architecture-reviewer` |
| **B3** | Refactor Dhan Factory dependencies | **Queue B** | B1, B2, B5 | Queue A complete | `code-reviewer` |
| **B4** | Refactor Upstox Builder encapsulation | **Queue B** | B1, B2, B5 | Queue A complete | `code-reviewer` |
| **B5** | Map raw exceptions to `AdapterException` | **Queue B** | B3, B4 | Queue A complete | `broker-auditor` |
| **C1** | Implement Upstox port methods | **Queue C** | C2, C3 | B1, B2, B5 | `broker-auditor` |
| **C2** | Remove/Integrate async HTTP client | **Queue D** | C3 | B5 | `code-reviewer` |
| **C3** | Encapsulate options TypedDict | **Queue D** | C2 | B1 | `quant-platform-reviewer`|
| **C4** | Wire heartbeat timeouts in WS | **Queue C** | C1 | B3, B5 | `reliability-reviewer`  |

---

## 4. Work Allocation & Loop Execution Protocols

Each queue is mapped to the **Autoresearch Git-Ratchet Loop** using our runner tool. For each task, the assigned agent follows the test-first, git-commit-on-success loop:

### Step 1: Configuration (`config.json`)
The orchestrator configures the loop harness:
```json
{
  "target_files": ["[target_file.py]"],
  "evaluation_command": "pytest [target_test_file.py] && mypy [target_file.py] && ruff check [target_file.py]"
}
```

### Step 2: Test & Implement
1.  **Test First**: Before editing target files, create a test case illustrating the issue (e.g. testing for type mismatches, LSP violations, or mock failures).
2.  **Edit Target**: The `thinking-proposer` makes targeted corrections.
3.  **Run Ratchet Harness**:
    ```bash
    python .autoresearch/harness_runner.py
    ```
4.  If successful, the change is committed to Git and the baseline metric is updated. If failed, it is automatically rolled back.

---

## 5. Risk Register & Mitigations

| Risk | Trigger | Impact | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **R1: Adapter Breakage** | Incompatible method signatures in adapters | Code compile failure / crash | Compile and type-check with `mypy` before committing (Gate A3). |
| **R2: Mock Divergence** | Modifying interfaces breaks existing unit tests | Test suite failures | Ensure existing test mocks are updated to align with LSP signature updates. |
| **R3: Token Expiry** | Live session token refresh fails on type mismatches | Connection drop in production | Verify that `token_manager.py` OAuth updates conform strictly to `PkcePair` types. |
| **R4: WS Data Loss** | Heartbeat listener blocks price feed thread | Latency increase | Run WebSocket thread safety tests in `test_websocket_thread_safety.py`. |

---

## 6. Required Architectural Decision Records (ADRs)

1.  **ADR-008: Exception Normalization Policy**
    *   *Decision*: All raw broker-native exceptions (Dhan/Upstox/HTTP) must be caught at the adapter gateway layer and mapped to a unified `AdapterException` containing standard error codes.
2.  **ADR-009: Dependency Inversion for Broker Factories**
    *   *Decision*: Monkey-patching configuration onto connection objects is banned. All dependencies must be injected through constructors during instantiation to maintain strict encapsulation.
