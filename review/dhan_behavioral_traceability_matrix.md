# Dhan Behavioral Traceability Matrix

**Date:** 2026-07-03  
**Chain:** Archived Feature → Archived Tests → Modern Implementation → Modern Tests → Verification Status

## Status Codes

| Code | Meaning |
|------|---------|
| **AC** | Already Covered — full chain intact |
| **EC** | Equivalent Coverage — different test, same assertion |
| **PC** | Partial Coverage |
| **MC** | Missing Coverage |
| **OB** | Obsolete — archive-only pattern |
| **NR** | Needs Rewrite — test exists but wrong target |
| **NAT** | Needs Additional Tests |

---

## P0 Regression Manifest (23 cases)

Source: [`archive/brokers/dhan/tests/regression/manifest.py`](../archive/brokers/dhan/tests/regression/manifest.py)

| ID | Capability | Archive Test | Modern Impl | Modern Test | Status |
|----|------------|--------------|-------------|-------------|--------|
| nse_ltp | supports_live_market_data | `manifest._assert_nse_ltp` via `test_regression_suite.py` | `DhanMarketData.ltp()` | `test_dhan_adapter.py` (mocked) | **PC** — no live P0 assertion |
| nse_quote | supports_live_market_data | manifest | `DhanMarketData.quote()` | `test_dhan_adapter.py` | **PC** |
| nse_depth_rest | supports_depth | manifest | `DhanMarketData.depth()` | None | **MC** |
| nse_depth_both_sides_fix | supports_depth | manifest | `DhanMarketData.depth()` | None | **MC** |
| nse_history_daily | supports_historical_data | manifest `gw.history()` DataFrame | `DhanHistorical.get_historical_candles()` | `test_dhan_historical.py` | **NR** — return type differs |
| index_ltp | supports_live_market_data | manifest | `DhanMarketData.ltp("NIFTY","INDEX")` | None | **MC** |
| nfo_option_chain_nifty | supports_option_chain | manifest | `DhanOptions` | `test_dhan_adapter.py` partial | **PC** |
| nfo_option_chain_banknifty | supports_option_chain | manifest | `DhanOptions` | None | **MC** |
| nfo_future_chain_nifty | supports_futures | manifest | `DhanFutures` | None | **MC** |
| nfo_future_chain_reliance | supports_futures | manifest | `DhanFutures` | None | **MC** |
| portfolio_funds | supports_portfolio | manifest | `DhanPortfolio.funds()` | `test_dhan_adapter.py` | **PC** |
| portfolio_positions | supports_portfolio | manifest | `DhanPortfolio.positions()` | `test_dhan_adapter.py` | **PC** |
| portfolio_holdings | supports_portfolio | manifest | `DhanPortfolio.holdings()` | None | **MC** |
| batch_ltp | supports_batch | manifest `ltp_batch()` | `DhanMarketData` batch methods | None | **MC** |
| nse_instruments_search | supports_instruments | manifest | `DhanInstruments.search()` | `test_dhan_identity.py` | **PC** |
| observability_cb | observability | manifest `gw.health()` | `DhanGateway.health()` | None | **PC** — missing WS status |
| subscription_engine_wired | architecture | manifest checks `_conn.subscription_engine` | `subscription_engine.py` | `test_dhan_phase3.py` | **EC** |
| session_manager_wired | architecture | manifest checks `_session_manager` | None | None | **MC** |
| stream_order_not_market_alias | architecture | manifest | `order_stream` property | `test_dhan_websockets.py` | **PC** |
| nfo_stock_option_chain | supports_option_chain | manifest | `DhanOptions` | None | **MC** |
| nfo_banknifty_future | supports_futures | manifest | `DhanFutures` | None | **MC** |
| depth_20_both_sides | supports_depth_20_ws | manifest (market hours) | `DhanDepth20Stream` | `test_dhan_websockets.py` | **NAT** — needs live case |
| full_mode_tick | supports_live_market_data | manifest (market hours) | `DhanStreaming` | `test_dhan_websockets.py` unit only | **NAT** |

**P0 manifest summary:** 0 AC | 8 PC | 12 MC | 0 EC full | 3 NR/NAT

---

## P0 Money-Path Features

| Feature | Archive Impl | Archive Tests | Modern Impl | Modern Tests | Status |
|---------|--------------|---------------|-------------|--------------|--------|
| Order idempotency | `OrdersAdapter` + `IdempotencyCache` | `test_orders_idempotency.py`, `test_broker_contract.py:214`, `test_live_validation.py:179` | `DhanOrders` — **none** | None | **MC** |
| TOTP cooldown guard | `DhanTotpClient` + `TotpCooldownGuard` | `test_token_bootstrap_policy.py`, factory tests | `DhanAuth` — **none** | `test_dhan_auth_state.py` (state only) | **MC** |
| expected_segment | `identity.resolve_ref()` | `test_resolver.py`, `test_symbol_mapping.py` | **none** | `test_dhan_identity.py` (basic) | **MC** |
| Cancel DELETE + parse | `OrdersAdapter.cancel_order()` | `test_orders.py` | POST + post-check | `test_dhan_adapter.py` cancel mock | **PC** |
| Pre-trade lot validation | `OrdersAdapter._validate` | `test_orders.py`, `test_live_validation.py` | **none** | None | **MC** |
| Risk manager gate | `OrdersAdapter` | architecture tests | **none** | None | **MC** |
| Kill switch | `OrdersAdapter.kill_switch()` | `test_orders.py` | **none** | None | **MC** |
| Slice orders | `place_slice_order()` | `test_orders.py` | **none** | None | **MC** |

---

## Archive Unit Tests → Modern Mapping (54 modules)

| Archive Unit Test | Primary Behavior | Modern Module | Modern Test | Status |
|-------------------|------------------|---------------|-------------|--------|
| test_alerts_adapter | Alerts CRUD | `alerts.py` | None | **MC** |
| test_architecture_regression | Wiring invariants | `gateway.py` | `test_dhan_gateway.py` assembly | **PC** |
| test_cache_refresh | Instrument TTL cache | **none** (no disk cache) | None | **MC** |
| test_chaos | Fault injection | resilience stack | `test_circuit_breaker_regression.py` | **PC** |
| test_circuit_breaker_regression | CB states | `http.py` + resilience | `test_circuit_breaker_regression.py` | **EC** |
| test_conditional_triggers | Trigger CRUD | `conditional_triggers.py` | None | **MC** |
| test_connection | DhanConnection lifecycle | `gateway.py` + `connection_lifecycle.py` | None | **PC** |
| test_depth_200_websocket | Depth200 WS parse | `depth200.py` | `test_dhan_websockets.py` | **PC** |
| test_depth_20_websocket | Depth20 WS parse | `depth20.py` | `test_dhan_websockets.py` | **PC** |
| test_depth_feeds | Shared depth base | `depth_feed_base.py` | `test_dhan_websockets.py` | **PC** |
| test_domain | Domain models | `brokers/domain/` shared | `test_domain_entities.py` | **EC** |
| test_edge_cases | Cross-cutting edges | various | `test_edge_cases.py` | **PC** |
| test_edis | EDIS authorize flow | `edis.py` (different API) | None | **NR** |
| test_exit_all | Panic close positions | `exit_all.py` | None | **MC** |
| test_factory | BrokerFactory.create | `DhanGateway.__init__` | `test_dhan_gateway.py` | **NR** |
| test_factory_auth | Auth wiring | `auth.py` | `test_dhan_auth_state.py` | **PC** |
| test_factory_websocket_wiring | WS token broadcast | `gateway.py` broadcast | `test_dhan_cross_cutting.py` | **EC** |
| test_forever_orders | Forever CRUD | `extensions/forever_orders.py` | `test_dhan_forever_orders.py` | **EC** |
| test_futures | Futures chain | `futures.py` | None | **MC** |
| test_gateway | Fat facade delegation | port properties | `test_dhan_adapter.py` protocol | **NR** |
| test_get_order_optimization | Direct GET by id | `orders.get_order()` | `test_dhan_adapter.py` | **PC** |
| test_historical | DataFrame history | `historical.py` Candle list | `test_dhan_historical.py` | **NR** |
| test_http_client | HTTP resilience | `http.py` | None dedicated | **MC** |
| test_http_client_circuit_breaker_split | Per-category CB | `create_circuit_breakers()` | `test_circuit_breaker_regression.py` | **EC** |
| test_ip_management | IP types PRIMARY/SEC | `ip_management.py` | None | **MC** |
| test_ledger | Typed ledger entries | `ledger.py` raw dict | None | **MC** |
| test_loader_cache_path | Disk cache path | **none** | None | **MC** |
| test_margin_adapter | Margin calc | `extensions/margin.py` | `test_dhan_margin.py` | **EC** |
| test_market_data | REST quotes | `market_data.py` | `test_dhan_adapter.py` | **PC** |
| test_options | Option chain | `options.py` | None | **MC** |
| test_order_factory_dhan_resolver | Factory+resolver | `identity.py` | `test_dhan_identity.py` | **PC** |
| test_orders | Order CRUD | `orders.py` | `test_dhan_adapter.py` | **PC** |
| test_orders_idempotency | Thread-safe idempotency | **none** | None | **MC** |
| test_portfolio | Portfolio fetch | `portfolio.py` | `test_dhan_adapter.py` | **PC** |
| test_publish_depth_strict | Depth tick validation | `depth_feed_base.py` | None | **MC** |
| test_publish_tick_strict | Tick validation | `streaming.py` | None | **MC** |
| test_real_websocket_payloads | Binary parse fixtures | `streaming.py` | `test_dhan_websockets.py` | **PC** |
| test_reconciliation | Drift + repair | `reconciliation.py` simplified | None | **MC** |
| test_reconnecting_service | WS reconnect | `reconnecting_service.py` | None | **MC** |
| test_resolver | Symbol resolve | `identity.py` | `test_dhan_identity.py` | **PC** |
| test_segments | Segment mapping | `config.py` EXCHANGE_MAP | None | **MC** |
| test_settings | Dynamic config loader | static `config.py` | `test_config_schema.py` generic | **NR** |
| test_status_mapper | Order status map | `mapper.py` | None | **MC** |
| test_super_orders | Super CRUD | `extensions/super_orders.py` | `test_dhan_super_orders.py` | **EC** |
| test_symbol_mapping | Symbol normalize | `identity.py` | `test_dhan_security_id.py` | **PC** |
| test_token_bootstrap_policy | Token bootstrap rules | `auth.py` | `test_dhan_auth_state.py` | **PC** |
| test_token_broadcast | Hot-swap tokens | `token_broadcast.py` | `test_token_broadcast.py` | **EC** |
| test_token_scheduler | Background refresh | `TokenRefreshScheduler` shared | `test_token_scheduler.py` | **EC** |
| test_token_scheduler_lifecycle | Scheduler start/stop | `gateway.close()` | `test_dhan_gateway.py` | **PC** |
| test_user_profile | Typed profile | `user_profile.py` | None | **MC** |
| test_websocket | WS connect/subscribe | `streaming.py` | `test_dhan_websockets.py` | **PC** |
| test_websocket_managed_service | ManagedService health | `depth_feed_base.health()` | None | **MC** |
| test_websocket_reconnect_recovery | Gap recovery | `reconnecting_service.py` | None | **MC** |
| test_websocket_reconnection | Reconnect backoff | `reconnecting_service.py` | None | **MC** |
| test_websocket_thread_safety | Concurrent subscribe | `subscription_engine.py` | None | **MC** |

---

## Archive Integration Tests → Modern Mapping (18 modules)

| Archive Integration Test | Behavior | Modern Test | Status |
|--------------------------|----------|-------------|--------|
| test_live_order_lifecycle | E2E order place/cancel | `test_live_order_lifecycle.py` | **PC** |
| test_live_quotes | Live REST quotes | None | **MC** |
| test_live_market_data_rest | REST market data | `test_dhan_adapter.py` mocked | **MC** |
| test_live_streaming | WS streaming | None live | **MC** |
| test_live_websocket | WS connect | `test_dhan_websockets.py` unit | **MC** |
| test_ws_parity | WS parity vs archive | None | **MC** |
| test_live_portfolio | Live portfolio | partial in adapter tests | **MC** |
| test_live_options | Options chain live | None | **MC** |
| test_live_derivatives_chain | Futures/options | None | **MC** |
| test_live_instruments | Instrument load | `test_dhan_security_id.py` | **PC** |
| test_live_batch_market_data | Batch LTP | None | **MC** |
| test_live_observability | Health endpoints | None | **MC** |
| test_symbol_mapping_live | Live symbol resolve | `test_dhan_security_id.py` | **PC** |
| test_endpoint_latency | Latency SLOs | None | **MC** |
| test_error_paths | API error handling | `test_edge_cases.py` | **PC** |
| test_schema_enforcement | Response schemas | None | **MC** |
| test_live_validation | Validation + idempotency live | None | **MC** |
| test_regression_suite | P0 manifest orchestrator | **none** | **MC** |

---

## Archive Contract & Regression Tests

| Test | Behavior | Modern | Status |
|------|----------|--------|--------|
| `contract/test_broker_contract.py` | Dhan-specific contract + idempotency | Generic fake protocol test | **NR** |
| `regression/test_coverage_manifest.py` | P0 case coverage gate | None | **MC** |
| `regression/test_e2e_smoke.py` | Smoke E2E | `test_dhan_adapter.py` | **PC** |
| `regression/test_recent_fixes.py` | Regression fixes | None | **MC** |

---

## Modern-Only Tests (no archive equivalent)

| Modern Test | Covers |
|-------------|--------|
| `test_dhan_phase3.py` | Phase 3 streaming/subscription wiring |
| `test_dhan_cross_cutting.py` | Token hot-swap across components |
| `test_infrastructure_waves.py` | GatewayRegistry (not Dhan-specific live) |
| `parity_validation.py` | Import smoke — **not behavioral** |

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Archive test modules | 78 |
| Modern Dhan test modules | 15 |
| P0 manifest cases | 23 |
| Full chain (AC) | 0 |
| Equivalent (EC) | 12 |
| Partial (PC) | 22 |
| Missing (MC) | 38 |
| Needs rewrite (NR) | 6 |
| Needs additional (NAT) | 3 |

**Gate rule:** No capability marked "Fully Replicated" until all five columns are green for that row.

**Minimum to upgrade verdict to CONDITIONALLY READY:**

1. Port all 23 P0 manifest cases to `brokers/tests/integration/adapters/dhan/test_regression_manifest.py`
2. Port `test_orders_idempotency.py` behaviors after implementation
3. Add `test_broker_contract.py` Dhan implementation (not fake adapter)
4. Wire `test_coverage_manifest.py` equivalent to fail CI on uncovered P0
