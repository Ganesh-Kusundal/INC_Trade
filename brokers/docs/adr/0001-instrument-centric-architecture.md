# ADR-0001: Instrument-Centric Architecture over Broker-Centric

- **Status**: Accepted
- **Date**: 2026-07-05
- **Deciders**: Elite Quantitative Engineering Review Board

## Context

The original `brokers/` architecture exposed a `BrokerGateway` interface
with many direct methods — `.place_order()`, `.quote()`, `.option_chain()`,
`.historical()`, `.subscribe()`, etc. As more broker adapters and use cases
were added, the gateway became a God Object: it accumulated dozens of
methods, mixed concerns (market data, trading, streaming, auth), and forced
every caller to know which broker they were talking to.

Concrete symptoms:

- Strategies and analytics code were peppered with `if broker == "dhan"` branches.
- Adding a new broker required touching the central gateway interface.
- Tests could not be expressed in terms of *what* the caller wanted to do;
  they were forced to assert against broker-specific method shapes.
- The mental model of a trader ("I want the quote for RELIANCE") was
  flattened into a procedural call chain on a transport-level object.

We needed a primary abstraction that matched the way traders, strategies,
and risk systems actually think about the domain — not the way HTTP
gateways happen to be structured.

## Decision

The **Instrument** is the primary domain abstraction. Brokers are
infrastructure. The public API is built around instruments and their
behaviour:

```python
import brokers

broker = brokers.connect("dhan", access_token="...", client_id="...")
inst = broker.market.instrument("NSE:RELIANCE")
quote = inst.quote()
chain = inst.option_chain()
broker.streaming.subscribe(inst.symbol, on_tick)
```

The `Instrument` entity in `brokers/market/instrument.py` is a frozen
dataclass that carries identity (`symbol`, `exchange`, `segment`), contract
metadata (`lot_size`, `tick_size`, `expiry`, `strike`, `option_type`), and
behavioural methods (`quote`, `historical`, `option_chain`,
`subscribe`). Brokers implement the ports; instruments are the value
objects that flow through those ports.

`brokers.connect()` is the composition root (`brokers/__init__.py`) and
returns a `BrokerSession` (`brokers/services/broker_session.py`) that
exposes named port properties (`orders`, `market`, `streaming`, `auth`,
`portfolio`, `historical`, `audit`) and a `MarketDataContext` that yields
instruments on demand.

## Consequences

**Positive**

- Rich domain objects are preferred over anemic services. Callers reason
  in domain terms ("the RELIANCE option chain") rather than transport terms
  ("a quote request to the Dhan gateway").
- Brokers become plugin implementations. The common interfaces are narrow
  and stable; new brokers only need to implement the ports.
- Tests can construct a single fake `Instrument` and assert on its
  behaviour, without re-implementing a gateway.
- A new dimension of use (e.g. a portfolio rebalancer, a scanner, a
  backtester) can be added as a method on `Instrument` without churning
  the gateway.

**Negative**

- The `Instrument` class must grow over time as more use cases are added.
  We accept this in exchange for not having a God Object.
- Some broker-specific methods cannot live on `Instrument` and instead
  live behind the `ExtensionRegistryPort` (see ADR-0004).
- There is a temporary period where the old `BrokerGateway` API coexists
  with the new `Instrument` API. A gateway-compat shim bridges them
  during migration (Phase 9).

## Alternatives Considered

- **Service-oriented only** — A `MarketService`, `OrderService`,
  `StreamingService` trio. Rejected: still broker-shaped, not domain-shaped;
  strategies end up threading the right service through their call graph.
- **Broker-only API** — Keep `BrokerGateway` and add more methods.
  Rejected: this is the status quo that produced the God Object. New
  methods had nowhere to go without bloating the interface.
- **OMS-only** — Push everything through an Order Management System.
  Rejected: OMS handles orders, not market data, not options, not history.
  Hiding every use case behind `place_order` would be a worse God Object.

## References

- `brokers/market/instrument.py` — `Instrument` value object.
- `brokers/services/broker_session.py` — `BrokerSession` composition root.
- `brokers/__init__.py` — `connect()` factory and public exports.
- `brokers/ARCHITECTURE_BLUEPRINT_V3.md` — Section 3, "Instrument-Centric
  Design".
