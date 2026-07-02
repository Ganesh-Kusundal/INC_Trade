# OMS crash recovery contract (REF-17)

The `OrderManager` keeps in-memory order state (`dict[str, Order]`). On process restart:

1. **Event log replay** rebuilds order/trade history from persisted `EventLog` entries.
2. **ProcessedTradeRepository** prevents duplicate fill application after reconnect.
3. **ReconciliationService** aligns local OMS state with broker order book on a fixed interval.

Full SQLite snapshot persistence is deferred; crash recovery correctness depends on durable event logging and reconciliation at startup.
