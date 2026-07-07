# V2 Architecture Implementation — Multi-Agent Dependency Graph

## Dependency Graph

```
Wave 1 (parallel, zero deps)
  ├── domain/enums.py          ← Exchange, AssetClass, Side, OrderType, etc.
  └── domain/exceptions.py     ← Domain exceptions
        │
Wave 2 (parallel, depends on Wave 1)
  ├── domain/values.py         ← Quote, Depth, Position, Balance, Trade, Holding, Greeks
  ├── domain/historical.py     ← HistoricalBar, HistoricalSeries, DateRange
  ├── domain/events.py         ← DomainEvent, EventType (refactor existing)
  └── domain/requests.py       ← OrderRequest, ModifyOrderRequest
        │
Wave 3 (parallel, depends on Wave 2)
  ├── domain/instrument.py     ← Rich Instrument aggregate root
  ├── domain/order.py          ← Order entity with lifecycle
  ├── domain/capabilities.py   ← ProviderCapabilities
  └── provider/__init__.py + provider/protocol.py  ← Provider Protocol
        │
Wave 4 (parallel, depends on Wave 3)
  ├── domain/account.py        ← Account aggregate root (risk inside)
  ├── domain/option_chain.py   ← OptionChain aggregate root
  ├── provider/routing.py      ← RoutingStrategy (function, not class)
  ├── provider/extensions.py   ← ExtensionAccess + typed Protocols
  └── risk.py                  ← RiskPolicy strategy
        │
Wave 5 (parallel, depends on Wave 4)
  ├── broker.py                ← Broker factory + DI entry point
  └── provider/composite.py    ← CompositeProvider (failover + routing)
        │
Wave 6 (parallel, depends on Wave 5)
  ├── brokers/dhan/dhan_provider.py     ← DhanProvider implements Provider
  ├── brokers/upstox/upstox_provider.py ← UpstoxProvider implements Provider
  └── brokers/paper/paper_provider.py   ← PaperProvider implements Provider
        │
Wave 7 (parallel, depends on Wave 6)
  ├── tests/architecture/test_no_code_smells.py   ← Ban wrappers, managers, anemia
  ├── tests/domain/test_instrument.py             ← Unit tests for rich Instrument
  ├── tests/domain/test_account.py                ← Unit tests for Account + risk
  └── tests/domain/test_option_chain.py           ← Unit tests for OptionChain
        │
Wave 8 (sequential)
  ├── Run mypy --strict
  ├── Run pytest
  └── Code review
```

## Parallel Execution Opportunities

| Wave | Files | Parallel? | Reason |
|------|-------|-----------|--------|
| 1 | 2 | ✅ | Zero cross-deps |
| 2 | 4 | ✅ | Only depend on Wave 1 enums |
| 3 | 4 | ✅ | Only depend on Wave 2 values |
| 4 | 5 | ✅ | Only depend on Wave 3 instrument/provider |
| 5 | 2 | ✅ | Only depend on Wave 4 |
| 6 | 3 | ✅ | Only depend on Wave 5 broker/composite |
| 7 | 4 | ✅ | Test files are independent |
| 8 | 3 | ✅ | Validation commands can run in parallel |

## Agent Team Assignments

- **Parent (Buffy)**: Writes all source files (agents can't write files), orchestrates waves
- **basher agents**: Run mypy, pytest, lint in parallel during validation
- **code-reviewer-glm**: Reviews changes after implementation
- **code-searcher**: Finds references to deleted types for migration
- **file-picker**: Finds test files that need updating
