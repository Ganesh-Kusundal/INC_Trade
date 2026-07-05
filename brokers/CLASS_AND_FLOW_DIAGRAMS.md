# Broker Platform — Class Diagrams & Flows

> Focused reference for class diagrams and runtime flows.
> All diagrams are derived from the actual codebase (1690 unit tests, 75 architecture tests passing).

---

## 1. Core Class Diagram — Domain & Bounded Contexts

```mermaid
classDiagram
    direction LR

    %% Domain Layer
    classDef domain fill:#e8f5e9,stroke:#2e7d32
    classDef port fill:#e3f2fd,stroke:#1565c0
    classDef market fill:#fff3e0,stroke:#ef6c00
    classDef trading fill:#fce4ec,stroke:#c2185b
    classDef service fill:#f3e5f5,stroke:#6a1b9a
    classDef adapter fill:#ffebee,stroke:#c62828
    classDef infra fill:#eceff1,stroke:#37474f

    namespace Domain {
        class Order {
            <<frozen>>
            +order_id: str
            +symbol: str
            +exchange: str
            +side: Side
            +quantity: int
            +status: OrderStatus
            +price: Decimal
            +order_type: OrderType
            +product_type: ProductType
            +validity: Validity
            +filled_quantity: int
            +correlation_id: str
            +validate()
            +is_active() bool
            +is_completed() bool
            +remaining_quantity() int
        }
        class Quote {
            <<frozen>>
            +symbol: str
            +ltp: Decimal
            +exchange: str
            +open, high, low, close: Decimal
            +volume: int
            +timestamp: datetime
            +seq_no: int
        }
        class MarketDepth {
            +symbol: str
            +bids: tuple
            +asks: tuple
            +exchange: str
            +timestamp: datetime
        }
        class Candle {
            +symbol: str
            +timestamp: datetime
            +open, high, low, close: Decimal
            +volume: int
        }
        class Trade {
            +trade_id: str
            +order_id: str
            +symbol: str
            +side: Side
            +quantity: int
            +price: Decimal
        }
        class Position {
            +symbol: str
            +quantity: int
            +average_price: Decimal
            +unrealized_pnl: Decimal
            +realized_pnl: Decimal
            +pnl_percentage() Decimal
            +is_profitable() bool
        }
        class Holding {
            +symbol: str
            +quantity: int
            +average_price: Decimal
            +isin: str
        }
        class Balance {
            +available_cash: Decimal
            +utilized_margin: Decimal
            +total_margin: Decimal
        }
        class OptionLeg {
            +symbol: str
            +ltp: Decimal
            +oi: int
            +iv: Decimal
            +delta: Decimal
            +theta: Decimal
            +gamma: Decimal
            +vega: Decimal
        }
        class OptionStrike {
            +strike: Decimal
            +call: OptionLeg
            +put: OptionLeg
        }
        class OptionChain {
            +underlying: str
            +expiry: str
            +spot: Decimal
            +strikes: tuple
        }
        class FillResult {
            +order_id: str
            +fill_price: Decimal
            +fill_quantity: int
            +is_complete: bool
        }
        class BrokerCapabilities {
            +broker_id: str
            +supports_*: bool
            +rate_limit_profiles: list
            +stream_limits: StreamLimitProfile
        }
    }

    namespace Ports {
        class MarketDataPort {
            <<protocol>>
            +ltp(symbol, exchange) Decimal
            +quote(symbol, exchange) Quote
            +depth(symbol, exchange) MarketDepth
            +ltp_batch(symbols, exchange) dict
            +quote_batch(symbols, exchange) dict
        }
        class HistoricalPort {
            <<protocol>>
            +get_historical_candles(...) list~Candle~
        }
        class HistoricalProvider {
            <<protocol>>
            +get_historical_candles(...) list
            +provider_id: str
            +is_available: bool
        }
        class StreamingPort {
            <<protocol>>
            +connect() async
            +disconnect() async
            +subscribe_quotes(symbols, exchange, callback) async
            +unsubscribe_quotes(symbols, exchange) async
        }
        class OrderExecutionPort {
            <<protocol>>
            +place_order(...) OrderResponse
            +modify_order(...) OrderResponse
            +cancel_order(...) OrderResponse
            +get_orderbook() list
        }
        class PortfolioPort {
            <<protocol>>
            +positions() list~Position~
            +holdings() list~Holding~
            +funds() Balance
            +trades() list~Trade~
        }
        class OptionsPort {
            <<protocol>>
            +get_option_chain(...) OptionChain
            +get_expiries(underlying, exchange) list
        }
        class InstrumentPort {
            <<protocol>>
            +search(query, limit) list
            +resolve(symbol, exchange) InstrumentInfo
            +load() None
        }
        class AuthPort {
            <<protocol>>
            +login() None
            +logout() None
            +refresh() None
        }
        class CachePort {
            <<protocol>>
            +get(key) Any
            +set(key, value, ttl) None
            +delete(key) bool
            +clear() None
        }
    }

    namespace Market {
        class Instrument {
            <<frozen, instrument-centric>>
            +symbol: str
            +exchange: str
            +segment: str
            +lot_size: int
            +tick_size: Decimal
            +expiry: datetime
            +strike: Decimal
            +option_type: str
            +composite_key: str
            +is_equity() bool
            +is_future() bool
            +is_option() bool
            +is_index() bool
            +is_call() bool
            +is_put() bool
            +is_expired() bool
            +is_expiring_soon() bool
            +days_to_expiry() int
            +validate_price(price) bool
            +validate_quantity(qty) bool
        }
        class InstrumentRegistry {
            <<thread-safe>>
            -RLock _lock
            -dict _instruments
            +get_or_create(key, factory)
            +get(key)
            +get_all() dict
        }
        class QuoteState {
            <<mutable>>
            +composite_key: str
            +ltp, bid, ask: Decimal
            +volume, oi: int
            +timestamp: datetime
            +seq_no: int
            +update_from_quote(quote)
            +snapshot() Quote
            +is_stale() bool
            +spread: Decimal
        }
        class DepthState {
            <<mutable>>
            +composite_key: str
            +bids, asks: list
            +update_from_depth(...)
            +snapshot() MarketDepth
        }
        class InstrumentHandle {
            -Instrument _instrument
            -MarketDataContext _context
            +symbol, exchange: str
            +quote() Quote
            +ltp() Decimal
            +depth() MarketDepth
            +ohlcv(start, end, res) list
            +history(start, end, res) list
            +option_chain(expiry) OptionChain
            +subscribe(callback) StreamHandle
            +unsubscribe() None
            +quote_state() QuoteState
            +metadata() dict
            +greeks() dict
            +oi() int
            +market_status() str
            +snapshot() Quote
        }
        class MarketDataContext {
            -InstrumentRegistry _registry
            -MarketDataPort _market_data
            -MarketRouter _market_router
            -HistoricalRouter _historical_router
            -StreamingPort _streaming
            -SubscriptionManager _subscription_manager
            -StreamingRouter _streaming_router
            -dict _quote_states
            +instrument(symbol, exchange) InstrumentHandle
            +quote(symbol, exchange) Quote
            +ltp(symbol, exchange) Decimal
            +depth(symbol, exchange) MarketDepth
            +ohlcv(...) list
            +option_chain(underlying, exchange, expiry) OptionChain
            +expiries(underlying, exchange) list
            +subscribe(symbol, exchange, callback)
            +unsubscribe(symbol, exchange)
            +quote_state(symbol, exchange) QuoteState
        }
        class MarketRouter {
            <<cache-first router>>
            -CachePort _cache
            -MarketDataPort _primary
            -list _fallbacks
            -dict _metrics
            +set_primary(provider)
            +add_fallback(provider)
            +quote(symbol, exchange) Quote
            +ltp(symbol, exchange) Decimal
            +depth(symbol, exchange) MarketDepth
            +quote_batch(symbols, exchange) dict
            +ltp_batch(symbols, exchange) dict
            +invalidate(symbol, exchange)
            +metrics() dict
        }
        class HistoricalRouter {
            -CachePort _cache
            -list~HistoricalProvider~ _providers
            +add_provider(provider)
            +fetch_candles(...) list
        }
        class StreamingRouter {
            -list~StreamingBackend~ _backends
            -dict _callbacks
            +add_backend(backend)
            +subscribe(key, exchange, callback)
            +unsubscribe(key, exchange, callback)
            +dispatch_tick(key, data)
            +disconnect_all()
        }
        class SubscriptionManager {
            <<thread-safe, ref-counted>>
            -RLock _lock
            -dict _ref_counts
            -dict _states
            -dict _callbacks
            +subscribe(key, exchange, callback)
            +unsubscribe(key, exchange, callback)
            +dispatch_tick(key, data)
            +is_subscribed(key) bool
        }
        class Scanner {
            +scan(criteria, symbols) ScanResult
            +scan_with_callback(criteria, cb, symbols) ScanResult
        }
        class ScanCriteria {
            <<protocol>>
            +matches(instrument, market_data) bool
        }
        class PriceAbove {
            -Decimal _threshold
            +matches(instrument, market_data) bool
        }
        class VWAPCalculator {
            -Decimal cumulative_pv
            -int cumulative_volume
            +update(trade)
            +value: Decimal
            +reset()
        }
        class GreeksCalculator {
            +single_leg(leg) dict
            +portfolio_greeks(positions) dict
        }
        class ReplayEngine {
            -float _speed
            -dict _candles_by_key
            +speed: float
            +load_csv(filepath)
            +ltp(symbol, exchange) Decimal
            +quote(symbol, exchange) Quote
            +get_historical_candles(...) list
            +provider_id: str
            +is_available: bool
        }
        class DegradedMode {
            -RLock _lock
            -dict _degraded
            +is_degraded(key) bool
            +enter_degraded(key)
            +recover(key)
            +degraded_keys() list
        }
    }

    namespace Trading {
        class Account {
            +account_id: str
            +broker_id: str
            +name: str
            +type: AccountType
            +status: AccountStatus
        }
        class AccountRegistry {
            <<thread-safe>>
            -RLock _lock
            -dict _accounts
            +register(account)
            +get(account_id)
            +get_all() dict
        }
        class AccountHandle {
            -Account _account
            -OrderExecutionPort _order_execution
            -PortfolioPort _portfolio
            -OrderManagementSystem _oms
            +place_order(...) OrderResponse
            +modify_order(order_id, ...) OrderResponse
            +cancel_order(order_id) OrderResponse
            +get_orders() list
            +positions() list
            +holdings() list
            +funds() Balance
            +trades() list
        }
        class TradingContext {
            -AccountRegistry _registry
            -OrderManagementSystem _oms
            -OrderRepository _order_repository
            +account(account_id) AccountHandle
            +default_account() AccountHandle
            +accounts() list
        }
        class OrderManagementSystem {
            <<Orchestrator>>
            -ExecutionRouter _router
            -OrderRepository _repository
            -bool _kill_switch
            -dict _idempotency_cache
            -dict _metrics
            +kill_switch: bool
            +place_order(account_id, ...) OrderResponse
            +modify_order(account_id, order_id, ...) OrderResponse
            +cancel_order(account_id, order_id) OrderResponse
            +get_order(account_id, order_id) Order
            +get_orderbook(account_id) list
            +get_active_orders(account_id) list
            +metrics() dict
        }
        class ExecutionRouter {
            <<thread-safe>>
            -RLock _lock
            -dict _adapters
            +register_adapter(broker_id, adapter)
            +place_order(account_id, ...) OrderResponse
            +modify_order(account_id, order_id, ...) OrderResponse
            +cancel_order(account_id, order_id) OrderResponse
            +get_orderbook(account_id) list
        }
        class OrderRepository {
            <<thread-safe>>
            -RLock _lock
            -dict _orders
            +save(order, account_id)
            +get(order_id)
            +get_active(account_id) list
            +update_status(order_id, status, ...)
        }
        class PortfolioAggregator {
            <<static>>
            +aggregate_positions(positions) ExposureSummary
            +aggregate_holdings(holdings) ExposureSummary
            +net_exposure_by_symbol(positions) dict
        }
        class ExposureSummary {
            +gross_exposure: Decimal
            +net_exposure: Decimal
            +unrealized_pnl: Decimal
            +by_symbol: dict
        }
    }

    namespace Services {
        class BrokerSession {
            <<composition root>>
            -Any _facade
            -Any _market
            -Any _trading
            +broker_id: str
            +market: MarketDataContext
            +trading: TradingContext
            +orders: Any
            +streaming: StreamingPort
            +auth: AuthPort
            +portfolio: PortfolioPort
            +historical: HistoricalPort
            +scanner: Scanner
            +replay: ReplayEngine
            +degraded_mode: DegradedMode
            +analytics: AnalyticsNamespace
            +close()
        }
        class BrokerFacade {
            <<backward compat>>
            +orders, market, portfolio: Any
            +place_order(...)
            +cancel_order(...)
            +get_quote(...)
            +get_balance()
            +close()
        }
    }

    %% Cross-layer relationships
    MarketDataPort ..> Quote
    MarketDataPort ..> MarketDepth
    HistoricalPort ..> Candle
    OrderExecutionPort ..> Order
    PortfolioPort ..> Position
    PortfolioPort ..> Holding
    PortfolioPort ..> Balance
    PortfolioPort ..> Trade
    OptionsPort ..> OptionChain

    InstrumentRegistry "1" --> "*" Instrument
    InstrumentHandle "1" --> "1" Instrument
    InstrumentHandle "1" --> "1" MarketDataContext
    MarketDataContext "1" --> "1" InstrumentRegistry
    MarketDataContext "1" --> "*" QuoteState
    MarketDataContext "1" --> "1" MarketRouter
    MarketDataContext "1" --> "1" HistoricalRouter
    MarketDataContext "1" --> "1" StreamingRouter
    MarketDataContext "1" --> "1" SubscriptionManager
    MarketRouter --> MarketDataPort
    HistoricalRouter --> HistoricalProvider
    StreamingRouter --> StreamingBackend
    SubscriptionManager --> QuoteState

    AccountRegistry "1" --> "*" Account
    AccountHandle "1" --> "1" Account
    TradingContext "1" --> "1" AccountRegistry
    TradingContext "1" --> "1" OrderManagementSystem
    AccountHandle --> OrderManagementSystem
    OrderManagementSystem --> ExecutionRouter
    OrderManagementSystem --> OrderRepository
    ExecutionRouter --> OrderExecutionPort
    ExecutionRouter --> PortfolioPort
    PortfolioAggregator ..> Position
    PortfolioAggregator ..> Holding

    Scanner --> ScanCriteria
    Scanner --> InstrumentRegistry
    Scanner --> MarketDataContext
    PriceAbove ..|> ScanCriteria
    VWAPCalculator --> Trade
    GreeksCalculator --> OptionLeg

    BrokerSession "1" --> "1" MarketDataContext
    BrokerSession "1" --> "1" TradingContext
    BrokerSession "1" --> "*" Scanner
    BrokerSession "1" --> "*" ReplayEngine
    BrokerSession "1" --> "*" DegradedMode

    class Order domain
    class Quote domain
    class MarketDepth domain
    class Candle domain
    class Trade domain
    class Position domain
    class Holding domain
    class Balance domain
    class OptionLeg domain
    class OptionStrike domain
    class OptionChain domain
    class FillResult domain
    class BrokerCapabilities domain
    class MarketDataPort port
    class HistoricalPort port
    class HistoricalProvider port
    class StreamingPort port
    class OrderExecutionPort port
    class PortfolioPort port
    class OptionsPort port
    class InstrumentPort port
    class AuthPort port
    class CachePort port
    class Instrument market
    class InstrumentRegistry market
    class QuoteState market
    class DepthState market
    class InstrumentHandle market
    class MarketDataContext market
    class MarketRouter market
    class HistoricalRouter market
    class StreamingRouter market
    class SubscriptionManager market
    class Scanner market
    class ScanCriteria market
    class PriceAbove market
    class VWAPCalculator market
    class GreeksCalculator market
    class ReplayEngine market
    class DegradedMode market
    class Account trading
    class AccountRegistry trading
    class AccountHandle trading
    class TradingContext trading
    class OrderManagementSystem trading
    class ExecutionRouter trading
    class OrderRepository trading
    class PortfolioAggregator trading
    class ExposureSummary trading
    class BrokerSession service
    class BrokerFacade service
```

---

## 2. Order Placement Flow (Detailed Sequence)

```mermaid
sequenceDiagram
    autonumber
    actor Trader
    participant Session as BrokerSession
    participant MDC as MarketDataContext<br/>(validation via Instrument)
    participant TC as TradingContext
    participant AH as AccountHandle
    participant OMS as OrderManagementSystem
    participant Val as Validators<br/>(domain)
    participant KS as Kill Switch
    participant Idem as Idempotency Cache
    participant ER as ExecutionRouter
    participant Adapter as OrderExecutionPort
    participant Repo as OrderRepository
    participant Bus as EventBus
    participant Bus2 as Subscribers
    participant OMS2 as Fill Detection
    participant QS as QuoteState<br/>(auto-update)

    Trader->>Session: place_order(symbol, exchange, side, qty)
    Session->>TC: account().place_order(...)
    TC->>AH: place_order(...)

    Note over AH: Check account status
    alt Account not ACTIVE
        AH-->>Trader: BrokerError
    else Account ACTIVE
        AH->>OMS: place_order(account_id, symbol, ...)

        Note over OMS: === Phase 1: Validation ===
        OMS->>Val: validate_order(symbol, exchange, qty, ...)
        Val->>Val: validate_symbol, validate_exchange,<br/>validate_quantity, validate_price,<br/>validate_trigger_price
        alt Validation fails
            Val-->>OMS: ValidationError
            OMS-->>AH: ValidationError
            AH-->>Trader: ValidationError
        else Validation passes
            OMS->>OMS: metrics.validation_failures NOT incremented

            Note over OMS: === Phase 2: Kill Switch ===
            OMS->>KS: is_kill_switch_active()
            alt Kill switch ON
                KS-->>OMS: True
                OMS->>OMS: metrics.orders_kill_switched++
                OMS-->>Trader: OrderResponse.fail(KILL_SWITCH_ACTIVE)
            else Kill switch OFF

                Note over OMS: === Phase 3: Idempotency ===
                OMS->>Idem: get(correlation_id)
                alt Idempotency HIT
                    Idem-->>OMS: cached OrderResponse
                    OMS->>OMS: metrics.idempotency_hits++
                    OMS-->>Trader: OrderResponse.already_executed(order_id)
                else Idempotency MISS

                    Note over OMS: === Phase 4: Route to broker ===
                    OMS->>ER: place_order(account_id, ...)
                    ER->>Adapter: place_order(symbol, exchange, side, qty, ...)

                    alt Adapter fails
                        Adapter-->>ER: raise
                        ER-->>OMS: raise
                        OMS->>OMS: metrics.broker_errors++
                        OMS-->>Trader: exception
                    else Adapter succeeds
                        Adapter-->>ER: OrderResponse(order_id, success, status)
                        ER-->>OMS: OrderResponse

                        Note over OMS: === Phase 5: Save to repository ===
                        OMS->>Repo: save(order, account_id)
                        alt Success
                            OMS->>OMS: metrics.orders_placed++
                        else Rejected
                            OMS->>OMS: metrics.orders_rejected++
                        end

                        Note over OMS: === Phase 6: Cache idempotency ===
                        alt correlation_id provided
                            OMS->>Idem: put(correlation_id, response)
                        end

                        Note over OMS: === Phase 7: Publish event ===
                        alt success=True
                            OMS->>Bus: publish(OrderPlacedEvent)
                        else success=False
                            OMS->>Bus: publish(OrderRejectedEvent)
                        end
                        Bus->>Bus2: notify subscribers

                        OMS-->>AH: OrderResponse
                        AH-->>TC: OrderResponse
                        TC-->>Session: OrderResponse
                        Session-->>Trader: OrderResponse
                    end
                end
            end
        end
    end

    Note over OMS2: === Asynchronous: Fill Detection ===
    OMS2->>OMS: on_fill(FillResult)
    OMS->>Repo: update_status(FILLED, filled_qty)
    OMS->>Bus: publish(OrderFilledEvent)
    Bus->>QS: update QuoteState
    Bus->>Bus2: notify subscribers
```

---

## 3. Market Data Quote Flow (Detailed)

```mermaid
sequenceDiagram
    autonumber
    actor Trader
    participant Handle as InstrumentHandle
    participant MDC as MarketDataContext
    participant MR as MarketRouter
    participant Cache as MemoryCache
    participant QSE as QuoteState<br/>(existing)
    participant Primary as Primary Provider<br/>(e.g., Dhan)
    participant Fallback as Fallback Provider<br/>(e.g., Replay)
    participant Bus as EventBus
    participant Stream as Streaming Adapter

    Trader->>Handle: inst.quote()
    Handle->>MDC: quote(symbol, exchange)
    MDC->>MR: quote(symbol, exchange)

    Note over MR: === Phase 1: Cache lookup ===
    MR->>Cache: get("quote:NSE:RELIANCE")

    alt Cache HIT (fresh, within TTL=2s)
        Cache-->>MR: cached Quote
        MR->>MR: metrics.quote_cache_hits++
        MR-->>MDC: Quote
        MDC-->>Handle: Quote
        Handle-->>Trader: Quote
    else Cache MISS or stale
        MR->>MR: metrics.quote_cache_misses++

        Note over MR: === Phase 2: Try primary provider ===
        MR->>Primary: quote(symbol, exchange)

        alt Primary succeeds
            Primary-->>MR: fresh Quote
        else Primary fails (e.g., timeout)
            Primary-->>MR: raise
            MR->>MR: metrics.provider_errors++

            Note over MR: === Phase 3: Try fallbacks ===
            loop For each fallback in order
                MR->>Fallback: quote(symbol, exchange)
                alt Fallback succeeds
                    Fallback-->>MR: Quote
                    Note over MR: stop trying more fallbacks
                else Fallback fails
                    Fallback-->>MR: raise
                end
            end
        end

        alt No provider succeeded
            MR-->>MDC: raise RuntimeError("No market data provider available")
            MDC-->>Handle: RuntimeError
            Handle-->>Trader: RuntimeError
        else Quote obtained
            Note over MR: === Phase 4: Populate cache ===
            MR->>Cache: set("quote:NSE:RELIANCE", quote, ttl=2s)

            MR-->>MDC: Quote
            MDC-->>Handle: Quote
            Handle-->>Trader: Quote
        end
    end

    Note over Stream: === Asynchronous: Streaming tick ===
    Stream->>QSE: update_from_quote(tick)
    QSE->>MR: invalidate(symbol, exchange)
    Note over MR: Next quote() call will fetch fresh data
    Stream->>Bus: publish(QuoteTickEvent)
```

---

## 4. Streaming Subscription Flow (Reference Counting)

```mermaid
sequenceDiagram
    autonumber
    actor ClientA as Client A
    actor ClientB as Client B
    participant Inst as Instrument
    participant MDC as MarketDataContext
    participant SM as SubscriptionManager
    participant State as SubscriptionState
    participant SR as StreamingRouter
    participant BE as Streaming Backend<br/>(WebSocket)
    participant Bus as EventBus
    participant QS as QuoteState

    Note over ClientA,ClientB: Both subscribe to the same instrument

    ClientA->>Inst: inst.subscribe(callback_A)
    Inst->>MDC: subscribe(symbol, exchange, callback_A)
    MDC->>SM: subscribe(key, exchange, callback_A)

    Note over SM: ref_count: 0 → 1
    SM->>State: transition(INACTIVE → SUBSCRIBING)
    SM->>SR: subscribe(key, exchange, callback_A)
    SR->>BE: backend.adapter.subscribe(key, exchange)
    SM->>State: transition(SUBSCRIBING → ACTIVE)
    SM->>SM: register callback_A in _callbacks[key]

    ClientB->>Inst: inst.subscribe(callback_B)
    Inst->>MDC: subscribe(symbol, exchange, callback_B)
    MDC->>SM: subscribe(key, exchange, callback_B)

    Note over SM: ref_count: 1 → 2 (no broker call)
    SM->>SM: register callback_B in _callbacks[key]

    Note over BE: WebSocket tick arrives
    BE->>SR: raw tick data
    SR->>SM: dispatch_tick(key, tick)

    Note over SM: Fan-out to all callbacks
    SM->>QS: update_from_quote(tick)
    QS->>MDC: notify (invalidate MarketRouter cache)
    SM->>Bus: publish(QuoteTickEvent)
    SM->>ClientA: callback_A(tick)
    SM->>ClientB: callback_B(tick)

    Note over ClientA,ClientB: Client A unsubscribes

    ClientA->>Inst: inst.unsubscribe()
    Inst->>MDC: unsubscribe(symbol, exchange)
    MDC->>SM: unsubscribe(key, exchange, callback_A)

    Note over SM: ref_count: 2 → 1 (no broker call)
    SM->>SM: remove callback_A from _callbacks[key]

    Note over ClientA,ClientB: Client B unsubscribes (last consumer)

    ClientB->>Inst: inst.unsubscribe()
    Inst->>MDC: unsubscribe(symbol, exchange)
    MDC->>SM: unsubscribe(key, exchange, callback_B)

    Note over SM: ref_count: 1 → 0
    SM->>State: transition(ACTIVE → UNSUBSCRIBING)
    SM->>SR: unsubscribe(key, exchange)
    SR->>BE: backend.adapter.unsubscribe(key, exchange)
    SM->>State: transition(UNSUBSCRIBING → INACTIVE)
    SM->>SM: cleanup _callbacks[key], _ref_counts[key], _states[key]
```

---

## 5. Historical Data Flow (Cache-First with Replay Fallback)

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Inst as Instrument
    participant MDC as MarketDataContext
    participant HR as HistoricalRouter
    participant Cache as MemoryCache
    participant P1 as Provider 1: Dhan
    participant P2 as Provider 2: Replay
    participant P3 as Provider 3: CSV

    Client->>Inst: inst.ohlcv(start, end, "1D")
    Inst->>MDC: ohlcv(symbol, exchange, start, end, resolution)
    MDC->>HR: fetch_candles(symbol, exchange, start, end, resolution)

    Note over HR: === Phase 1: Cache lookup ===
    HR->>Cache: get(key)

    alt Cache HIT
        Cache-->>HR: list~Candle~
        Note over HR: Filter to requested range
        HR-->>MDC: list~Candle~
        MDC-->>Inst: list~Candle~
        Inst-->>Client: list~Candle~
    else Cache MISS
        Note over HR: === Phase 2: Try providers ===
        loop For each provider in chain
            alt Provider available
                HR->>P1: get_historical_candles(...)
                P1-->>HR: list~Candle~
                Note over HR: Stop trying more providers
            else Provider not available
                Note over HR: Try next provider
            end
        end

        alt Provider 1: Dhan (succeeds)
            HR->>P1: get_historical_candles(...)
            P1-->>HR: list~Candle~ (live data)
        else Provider 1 fails, Provider 2: Replay
            HR->>P2: get_historical_candles(...)
            P2-->>HR: list~Candle~ (replay data)
        else Provider 1+2 fail, Provider 3: CSV
            HR->>P3: get_historical_candles(...)
            P3-->>HR: list~Candle~ (file data)
        end

        alt All providers failed
            HR-->>MDC: raise NotSupportedError
            MDC-->>Inst: NotSupportedError
            Inst-->>Client: NotSupportedError
        else Got data
            Note over HR: === Phase 3: Populate cache ===
            HR->>Cache: set(key, candles, ttl=86400s for 1D)

            HR-->>MDC: list~Candle~
            MDC-->>Inst: list~Candle~
            Inst-->>Client: list~Candle~
        end
    end
```

---

## 6. Authentication & Token Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Connect as brokers.connect()
    participant Auth as AuthPort<br/>(DhanAuth/UpstoxAuth)
    participant TokenStore as TokenStorePort
    participant API as Broker API
    participant Sched as TokenScheduler

    User->>Connect: connect("dhan", access_token="...", client_id="...")
    Connect->>Auth: initialize(credentials)

    Note over Auth: === Phase 1: Load existing token ===
    Auth->>TokenStore: load_token()
    alt Token exists
        TokenStore-->>Auth: stored_token
        Auth->>API: validate_token(stored_token)
        alt Token valid
            API-->>Auth: OK
        else Token invalid
            Note over Auth: === Phase 2: Re-authenticate ===
            Auth->>API: login(credentials)
            API-->>Auth: new_token
            Auth->>TokenStore: save(new_token)
        end
    else No token
        Auth->>API: login(credentials)
        API-->>Auth: new_token
        Auth->>TokenStore: save(new_token)
    end

    Connect-->>User: BrokerSession ready

    Note over Sched: === Phase 3: Background refresh ===
    loop Every 30 minutes
        Sched->>Auth: is_token_expiring_soon()
        alt Expiring within 1 hour
            Auth->>API: refresh_token()
            alt Refresh succeeds
                API-->>Auth: new_token
                Auth->>TokenStore: save(new_token)
                Auth->>Sched: publish(TokenRefreshed)
            else Refresh fails
                Auth->>Sched: publish(TokenExpired)
                Note over Auth: Trigger full re-auth
                Auth->>API: login(credentials)
            end
        end
    end

    User->>Connect: broker.close()
    Connect->>Sched: cancel()
    Connect->>Auth: cleanup()
```

---

## 7. Order Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> PENDING : place_order (initial)
    PENDING --> OPEN : broker acknowledges
    PENDING --> REJECTED : broker rejects immediately
    OPEN --> PARTIALLY_FILLED : partial fill reported
    OPEN --> FILLED : complete fill
    OPEN --> CANCELLED : user cancel_order
    OPEN --> REJECTED : broker cancels
    OPEN --> EXPIRED : validity timeout (DAY/IOC)
    PARTIALLY_FILLED --> FILLED : remaining quantity filled
    PARTIALLY_FILLED --> CANCELLED : user cancel_order
    PARTIALLY_FILLED --> REJECTED : broker cancels
    FILLED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
    EXPIRED --> [*]

    note right of PENDING : OMS initiated<br/>in OrderRepository
    note right of OPEN : OMS publishes<br/>OrderPlacedEvent
    note right of FILLED : OMS publishes<br/>OrderFilledEvent
    note right of CANCELLED : OMS publishes<br/>OrderCancelledEvent
    note right of REJECTED : OMS publishes<br/>OrderRejectedEvent
```

---

## 8. Subscription Lifecycle State Machine

```mermaid
stateDiagram-v2
    [*] --> INACTIVE
    INACTIVE --> SUBSCRIBING : first subscribe (ref_count: 0→1)
    SUBSCRIBING --> ACTIVE : backend.adapter.subscribe() OK
    SUBSCRIBING --> INACTIVE : backend.adapter.subscribe() fails

    ACTIVE --> ACTIVE : additional subscribe (ref_count: N→N+1)
    ACTIVE --> ACTIVE : tick dispatched (fan-out to all callbacks)
    ACTIVE --> ACTIVE : unsubscribe one of N (ref_count: N→N-1)

    ACTIVE --> UNSUBSCRIBING : last unsubscribe (ref_count: 1→0)
    UNSUBSCRIBING --> INACTIVE : backend.adapter.unsubscribe() OK

    INACTIVE --> INACTIVE : unsubscribe (no-op)

    note right of ACTIVE : _callbacks[key] may have<br/>multiple consumers
    note right of UNSUBSCRIBING : Cleanup: remove<br/>_ref_counts, _states, _callbacks
```

---

## 9. Connection Health State Machine (Degraded Mode)

```mermaid
stateDiagram-v2
    [*] --> HEALTHY
    HEALTHY --> HEALTHY : provider call succeeds
    HEALTHY --> DEGRADED : provider call fails
    HEALTHY --> DEGRADED : provider call raises (any exception)

    DEGRADED --> DEGRADED : serve stale cached data<br/>(emit ConnectionEvent)
    DEGRADED --> DEGRADED : subsequent calls fail<br/>(max_degraded_duration not elapsed)

    DEGRADED --> HEALTHY : provider call succeeds<br/>(auto-recover)
    DEGRADED --> AUTO_RECOVER : max_degraded_duration_s elapsed

    AUTO_RECOVER --> HEALTHY : transition to healthy

    note right of HEALTHY : quote/depth/ltp use live provider
    note right of DEGRADED : quote/depth/ltp serve from cache
    note right of AUTO_RECOVER : graceful transition<br/>without explicit success
```

---

## 10. Component Dependency Graph

```mermaid
graph TB
    subgraph "External"
        User[Application Code]
    end

    subgraph "Public API"
        Connect[brokers.connect]
        Session[BrokerSession]
    end

    subgraph "Bounded Context: Market"
        MDC[MarketDataContext]
        Inst[Instrument + Registry]
        MR[MarketRouter]
        HR[HistoricalRouter]
        SR[StreamingRouter]
        SM[SubscriptionManager]
        Scn[Scanner]
        Ana[Analytics]
        Deg[DegradedMode]
    end

    subgraph "Bounded Context: Trading"
        TC[TradingContext]
        AH[AccountHandle]
        OMS[OrderManagementSystem]
        ER[ExecutionRouter]
        Repo[OrderRepository]
        PA[PortfolioAggregator]
    end

    subgraph "Ports"
        PMD[MarketDataPort]
        PHist[HistoricalPort]
        PStr[StreamingPort]
        POrd[OrderExecutionPort]
        PPf[PortfolioPort]
        POpt[OptionsPort]
        PInst[InstrumentPort]
        PAuth[AuthPort]
        PCache[CachePort]
    end

    subgraph "Domain"
        D1[Order, Quote, Trade]
        D2[Instrument, OptionLeg, Candle]
        D3[Position, Holding, Balance]
        D4[Events, Capabilities]
    end

    subgraph "Infrastructure"
        Cache[MemoryCache]
        EB[EventBus]
        HTTP[HTTP Client]
        WS[WebSocket Pool]
    end

    subgraph "Adapters"
        Dhan[Dhan]
        Upstox[Upstox]
        Paper[Paper]
        Replay[ReplayEngine]
    end

    User --> Connect
    Connect --> Session
    Session --> MDC
    Session --> TC
    MDC --> MR
    MDC --> HR
    MDC --> SR
    MDC --> SM
    MDC --> Scn
    MDC --> Ana
    MDC --> Deg
    MDC --> Inst
    TC --> AH
    TC --> OMS
    TC --> ER
    TC --> Repo
    TC --> PA
    AH --> OMS
    OMS --> ER
    OMS --> Repo
    ER --> POrd
    MR --> PCache
    MR --> PMD
    HR --> PHist
    SR --> PStr
    PMD --> D1
    PHist --> D2
    POrd --> D1
    PPf --> D3
    POpt --> D1
    PAuth --> D1
    PCache --> Cache
    EB --> D4
    Dhan -.implements.-> PMD
    Dhan -.implements.-> PHist
    Dhan -.implements.-> PStr
    Dhan -.implements.-> POrd
    Dhan -.implements.-> PPf
    Upstox -.implements.-> PMD
    Upstox -.implements.-> PHist
    Upstox -.implements.-> PStr
    Upstox -.implements.-> POrd
    Upstox -.implements.-> PPf
    Paper -.implements.-> PMD
    Paper -.implements.-> POrd
    Paper -.implements.-> PPf
    Replay -.implements.-> PMD
    Replay -.implements.-> PHist
    Dhan --> HTTP
    Dhan --> WS
    Upstox --> HTTP
    Upstox --> WS

    style Domain fill:#e8f5e9
    style Ports fill:#e3f2fd
    style Market fill:#fff3e0
    style Trading fill:#fce4ec
    style Infrastructure fill:#eceff1
    style Adapters fill:#ffebee
```

---

## 11. Threading & Concurrency Model

```mermaid
graph TB
    subgraph "Main Application Thread"
        Main[User Code]
    end

    subgraph "WebSocket Reader Threads"
        WS1[WebSocket Thread 1]
        WS2[WebSocket Thread 2]
    end

    subgraph "Background Schedulers"
        TokenS[Token Refresh Scheduler]
        Heartbeat[WebSocket Heartbeat]
    end

    subgraph "Thread-Safe State"
        direction TB
        SubMgr[SubscriptionManager<br/>RLock + ref counts]
        SubState[SubscriptionState]
        InstReg[InstrumentRegistry<br/>RLock]
        ExecR[ExecutionRouter<br/>RLock]
        OrdRepo[OrderRepository<br/>RLock]
        OMS3[OMS<br/>RLock + idempotency_cache]
        EB2[EventBus<br/>Lock]
        Cache2[MemoryCache]
    end

    Main -.subscribe/unsubscribe.-> SubMgr
    Main -.get_or_create.-> InstReg
    Main -.place_order.-> ExecR
    Main -.save.-> OrdRepo
    Main -.place_order.-> OMS3

    WS1 -.raw tick.-> SubMgr
    WS2 -.raw tick.-> SubMgr
    SubMgr -.dispatch_tick.-> SubState
    SubMgr -.callback.-> Main

    TokenS -.refresh.-> EB2
    Heartbeat -.ping/pong.-> WS1

    OMS3 -.uses.-> OrdRepo
    OMS3 -.uses.-> ExecR
    OMS3 -.uses.-> EB2
    SubMgr -.uses.-> Cache2
    ExecR -.uses.-> Cache2

    style Main fill:#e3f2fd
    style SubMgr fill:#fff3e0
    style InstReg fill:#fff3e0
    style ExecR fill:#fff3e0
    style OrdRepo fill:#fff3e0
    style OMS3 fill:#fff3e0
    style EB2 fill:#fff3e0
    style Cache2 fill:#fff3e0
```

---

## 12. Memory & Identity Model

```mermaid
graph LR
    subgraph "Process Memory (one per process)"
        subgraph "Singletons (canonical identity)"
            Inst1[Instrument<br/>NSE:RELIANCE]
            Inst2[Instrument<br/>NSE:TCS]
            Inst3[Instrument<br/>NFO:NIFTY 18000 CE]
        end

        subgraph "Mutable State (one per instrument)"
            QS1[QuoteState<br/>NSE:RELIANCE]
            QS2[QuoteState<br/>NSE:TCS]
        end

        subgraph "Per Subscription"
            Sub1[SubscriptionState<br/>NSE:RELIANCE]
        end

        subgraph "Per Account"
            Acc1[Account<br/>dhan/default]
            Acc2[Account<br/>upstox/primary]
        end

        subgraph "Per Order"
            Ord1[Order<br/>PAPER-A1B2]
            Ord2[Order<br/>DHAN-123]
        end

        subgraph "Per Session"
            Sess[BrokerSession]
            MR[MarketRouter]
            ER[ExecutionRouter]
            Bus[EventBus]
        end
    end

    Inst1 -.identity.-> Inst1
    Inst1 --> QS1
    QS1 --> Sub1
    Acc1 --> Ord1
    Acc1 --> Ord2
    Sess --> MR
    Sess --> ER
    Sess --> Bus

    note["Identity invariants:<br/>• InstrumentRegistry.get_or_create<br/>  returns SAME object for SAME key<br/>• Order, Quote, OptionLeg are frozen<br/>  (immutable, thread-safe by value)<br/>• QuoteState, DepthState are mutable<br/>  but protected by RLock"]
```

---

## 13. Public API Surface

```mermaid
graph TB
    Start[import brokers]
    Start --> Connect[brokers.connect]
    Start --> Domain[brokers.domain entities]

    Connect -->|name, **credentials| Sess[BrokerSession]

    Sess --> P1[broker.market]
    Sess --> P2[broker.trading]
    Sess --> P3[broker.orders]
    Sess --> P4[broker.streaming]
    Sess --> P5[broker.auth]
    Sess --> P6[broker.portfolio]
    Sess --> P7[broker.historical]
    Sess --> P8[broker.extensions]
    Sess --> P9[broker.capabilities]
    Sess --> P10[broker.scanner]
    Sess --> P11[broker.replay]
    Sess --> P12[broker.degraded_mode]
    Sess --> P13[broker.analytics]

    P1 --> Inst[market.instrument]
    Inst --> IH[InstrumentHandle]
    IH --> M1[inst.quote]
    IH --> M2[inst.depth]
    IH --> M3[inst.ohlcv]
    IH --> M4[inst.history]
    IH --> M5[inst.option_chain]
    IH --> M6[inst.subscribe]
    IH --> M7[inst.metadata]
    IH --> M8[inst.greeks]
    IH --> M9[inst.oi]
    IH --> M10[inst.market_status]

    P2 --> Acc[trading.account]
    Acc --> AH[AccountHandle]
    AH --> A1[place_order]
    AH --> A2[modify_order]
    AH --> A3[cancel_order]
    AH --> A4[positions]
    AH --> A5[holdings]
    AH --> A6[funds]
    AH --> A7[trades]

    P10 --> Scan[scanner.scan]
    P13 --> Anal[analytics namespace]
    Anal --> AN1[vwap]
    Anal --> AN2[greeks]
    Anal --> AN3[atr]
    Anal --> AN4[volume_profile]
```

---

## 14. Failure Modes & Resilience

```mermaid
graph LR
    subgraph "Failure Scenarios"
        F1[Broker API down]
        F2[WebSocket disconnect]
        F3[Token expired]
        F4[Rate limited]
        F5[Stale data]
        F6[Validation failure]
    end

    subgraph "Resilience Mechanisms"
        R1[DegradedMode<br/>serve stale cache]
        R2[Auto-reconnect<br/>exponential backoff]
        R3[Token refresh<br/>background scheduler]
        R4[Rate limiter<br/>token bucket]
        R5[Cache TTL<br/>stale-while-revalidate]
        R6[Domain validators<br/>in OMS]
    end

    subgraph "Observability"
        O1[OMS metrics<br/>orders_placed, kill_switched]
        O2[MarketRouter metrics<br/>cache_hits, provider_errors]
        O3[Event bus<br/>ConnectionEvent, TokenExpired]
        O4[OTEL spans<br/>distributed tracing]
    end

    F1 --> R1
    F1 --> R2
    F1 -.emits.-> O3
    F2 --> R2
    F2 -.emits.-> O3
    F3 --> R3
    F3 -.emits.-> O3
    F4 --> R4
    F4 -.tracks.-> O1
    F5 --> R5
    F5 --> R1
    F6 --> R6
    F6 -.tracks.-> O1

    R1 -.tracks.-> O2
    R3 -.tracks.-> O2
    R4 -.tracks.-> O2
```

---

## 15. Architecture Fitness Functions (26 CI-Enforced)

| Category | Test | What It Enforces |
|----------|------|------------------|
| **Layer Boundaries** | `TestBoundaryRules` | Domain/ports/services/market/trading cannot import forbidden layers |
| **Port Structure** | `TestPortStructure` | All 21 ports must be `@runtime_checkable Protocol` |
| **Exception Hierarchy** | `TestExceptionHierarchy` | All exceptions inherit from `TradeXV2Error` |
| **Error Code Coverage** | `TestErrorCodeCoverage` | All error codes are referenced in exceptions.py |
| **API Hygiene** | `TestNoDuplicateAll`, `TestNoCompatGateways` | No duplicate exports, no deprecated gateway files |
| **Infrastructure** | `TestInfrastructureBoundary`, `TestNoRawDictInDomain` | Infrastructure doesn't import adapters, no raw dict fields |
| **Single Source of Truth** | `TestSingleIdempotencyImplementation`, `TestSingleEndpointAuthority` | Idempotency in core/, no duplicate endpoint files |
| **Singleton Discipline** | `TestNoGlobalSingletons` | No class-level `_instances` outside allowed paths |
| **Capability Design** | `TestCapabilityConstants` | All capability constants in ALL_CAPS, no duplicates |
| **Type Safety** | `TestNoHasattrOnGateway`, `TestServiceConstructorArgLimit` | No `hasattr()` in facade, services ≤5 init params |
| **DIP Enforcement** | `TestNoAdapterImportsService`, `TestServiceLayer` | Adapters don't import services, services don't import adapters |
| **Contract Tests** | `TestBrokerGatewayContract`, `TestHttpClientPort` | All gateways have required properties, adapters use port abstractions |
| **Bounded Contexts** | `TestMarketTradingBoundary`, `TestTradingBoundaryNoServices` | Market/trading isolated, trading doesn't import services/infra/adapters |
| **Identity Guarantees** | `TestOneInstrumentPerSymbol` | Same key returns same object (10-thread stress test) |
| **DIP (No DTO Leakage)** | `TestNoBrokerDtoLeakage` | Domain/ports don't import from adapters |
| **Extension Isolation** | `TestExtensionIsolation` | Broker-specific protocols not in `ports/__init__.py` |
| **API Stability** | `TestNoBrokerGatewayInPorts` | `BrokerGateway` moved from ports to services |
| **Router Boundary** | `TestRouterBoundary` | Routers don't import adapters/infrastructure |
| **No Broker Leakage** | `TestNoBrokerInternalDataLeakage` | Domain/market don't use Dhan's `security_id`, Upstox's `instrument_key` |

**Total: 26 fitness function classes, 75 architecture tests, 0 failures.**

---

## 16. Diagram Conventions

| Convention | Meaning |
|------------|---------|
| `<<frozen>>` | Immutable dataclass (no mutation after construction) |
| `<<protocol>>` | `@runtime_checkable Protocol` interface |
| `<<mutable>>` | Mutable state object (thread-safe) |
| `<<Orchestrator>>` | Coordinates multiple collaborators |
| `<<composition root>>` | Top-level factory that wires all dependencies |
| `<<static>>` | Static utility class (no instance state) |
| Green boxes | Domain layer (no external deps) |
| Blue boxes | Ports layer (interfaces only) |
| Orange boxes | Market context |
| Pink boxes | Trading context |
| Purple boxes | Service layer |
| Red boxes | Adapters |
| Gray boxes | Infrastructure |

---

*For complete file listing and architecture details, see `ARCHITECTURE_DIAGRAMS.md` (the main file).*
*For test coverage, see `TESTING_STRATEGY.md`.*
