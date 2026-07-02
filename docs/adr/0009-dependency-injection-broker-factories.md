# ADR-009: Dependency Inversion for Broker Factories — No Post-Construction Mutation

All dependencies required by a broker connection object (`DhanConnection`, `UpstoxBroker`,
etc.) must be injected through the constructor at instantiation time. Monkey-patching
private attributes after construction (e.g. `connection._auth = auth`) is banned.

**Status**: accepted

## Rationale

Post-construction attribute mutation produces objects that exist in an invalid intermediate
state between instantiation and the monkey-patch. This means:

1. Type checkers (mypy) cannot verify the attribute exists, producing `attr-defined` errors.
2. Tests that construct the object without running the full factory path silently get an
   incomplete object, leading to false-negative test results.
3. The factory becomes an implicit, hidden initialization protocol — a future maintainer
   reading the constructor sees no hint that `_auth` is expected to exist.

Constructor injection makes all dependencies visible, checkable, and testable in isolation.

## Considered Options

- **`__post_init__` hooks** — rejected; still hides the dependency from the public API.
- **`configure(auth=...)` method** — rejected; still allows partially-initialized state.
- **Constructor parameter** — chosen; enforced by mypy from day one.

## Consequences

- `DhanConnection.__init__` now accepts `auth: AuthManager | None = None` and constructs
  `_session_manager` internally when `auth` is provided.
- The factory passes `auth=auth` to the constructor rather than setting `connection._auth`
  after the fact.
- The `UpstoxBrokerBuilder` pattern is preserved (builder is called from `__init__`) but
  all attributes the builder will set must be pre-declared (as `None` sentinels with
  explicit types) in `UpstoxBroker.__init__` before `builder.build()` is called.
- Any new broker factory code must be reviewed for post-construction mutation; the PR
  checklist should include "are all constructor parameters injected, not patched?".
