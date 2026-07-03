# Upstox Test Traceability Matrix

| Archived Feature | Archived Test File | Modern Test File | Status |
|------------------|-------------------|------------------|--------|
| OAuth PKCE | `archive/.../test_pkce.py` | `brokers/tests/unit/adapters/upstox/test_pkce.py` | Equivalent Coverage |
| OAuth client | `archive/.../test_oauth_client.py` | `brokers/tests/unit/adapters/upstox/test_oauth_client.py` | Equivalent Coverage |
| TOTP bootstrap | `archive/.../test_totp_bootstrap.py` | `brokers/tests/unit/adapters/upstox/test_totp_bootstrap.py` | Equivalent Coverage |
| Token manager | `archive/.../test_token_manager.py` | `brokers/tests/unit/adapters/upstox/test_token_manager.py` | Equivalent Coverage |
| TOTP scheduler | `archive/.../test_totp_scheduler.py` | `brokers/tests/unit/adapters/upstox/test_totp_scheduler.py` | Equivalent Coverage |
| Redirect server | `archive/.../test_redirect_server.py` | `brokers/tests/unit/adapters/upstox/test_redirect_server.py` | Equivalent Coverage |
| HTTP 401 retry | `archive/.../test_http_client.py` | `brokers/tests/unit/adapters/upstox/test_http_client.py` | Equivalent Coverage |
| Feed authorizer | `archive/.../test_architecture_regression.py` | `brokers/tests/unit/adapters/upstox/test_feed_authorizer.py` | Partial Coverage |
| WS token refresh | `archive/.../test_websocket_reconnect_recovery.py` | `brokers/tests/unit/adapters/upstox/test_streaming_auth.py` | Partial Coverage |
| Order placement | `archive/.../test_gateway_order_placement.py` | `brokers/tests/integration/test_upstox_adapter.py` | Partial Coverage |
| Cancel fill race | `archive/.../gateway.py` H1 | `brokers/tests/unit/adapters/upstox/test_orders_safety.py` | Equivalent Coverage |
| Order idempotency | `archive/.../test_order_command_adapter.py` | `brokers/tests/unit/adapters/upstox/test_orders_safety.py` | Partial Coverage |
| Instrument loader | `archive/.../test_instrument_loader.py` | `brokers/tests/integration/test_upstox_instruments.py` | Partial Coverage |
| Instrument resolver | `archive/.../test_upstox_resolver.py` | `brokers/tests/integration/test_upstox_instruments.py` | Partial Coverage |
| GTT adapter | `archive/.../test_gtt_adapter.py` | — | Needs Additional Tests |
| WS live parity | `archive/.../test_ws_parity.py` | `brokers/tests/integration/test_upstox_ws_parity.py` | Equivalent Coverage (gated) |
| Live quotes | `archive/.../test_live_quotes.py` | — | Needs Additional Tests |
| Live portfolio | `archive/.../test_live_portfolio.py` | `brokers/tests/integration/test_upstox_adapter.py` | Partial Coverage (mocked) |
| Option chain live | `archive/.../test_live_derivatives_chain.py` | — | Needs Additional Tests |
| Extended APIs | `archive/.../test_live_extended.py` | — | Needs Additional Tests |
| Endpoint latency | `archive/.../test_endpoint_latency.py` | — | Needs Additional Tests |
| Contract suite | `archive/.../test_upstox_contract.py` | `brokers/tests/integration/test_gateway_contracts.py` | Partial Coverage |

**Summary:** Auth subsystem at equivalent coverage. Order safety and HTTP refresh newly covered. Live integration suite partially ported (mocked + WS parity gate). GTT, derivatives, extended APIs, and latency benchmarks need additional live tests.
