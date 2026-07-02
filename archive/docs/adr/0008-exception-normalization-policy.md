# ADR-008: Exception Normalization at the Gateway Boundary

All raw broker-native exceptions (Dhan SDK errors, Upstox HTTP errors, provider-specific
network faults) must be caught at the adapter gateway layer — never propagated beyond it.
The gateway converts every caught exception into a structured log entry (at minimum
`logger.warning(...)` with symbol, exchange, and error context) before returning a safe
fallback value (`OrderResponse.fail(...)`, `pd.DataFrame()`, etc.).

**Status**: accepted

## Rationale

Provider-specific exceptions are implementation details of the adapter layer. Leaking them
into callers (strategy engine, CLI, API layer) creates tight coupling: the caller must know
which broker is active to catch the right exception type, which violates the
broker-agnostic contract of `MarketDataGateway`.

Structured logging at the boundary gives operators full diagnostic visibility without
forcing callers to handle provider internals.

## Consequences

- Every `except Exception:` or `except <ProviderError>:` block in gateway classes **must**
  include a `logger.warning(...)` call before returning a fallback — silent swallowing is banned.
- Lazy in-method exception imports (e.g. `from brokers.dhan.exceptions import X` inside a
  method body) are banned; all exception types used in a module must be imported at the
  module top-level so they appear in static analysis.
- Future adapters (new brokers) must follow this pattern from day one; the code reviewer
  checklist should include "does every except block log before returning?".
