# Upstox Parity Implementation Sign-Off

**Date:** 2026-07-03  
**Verdict:** CONDITIONALLY READY FOR STAGING

## Layer 0 — Critical (Complete)

- [x] `UpstoxFeedAuthorizer` ported — [`brokers/adapters/upstox/feed_authorizer.py`](brokers/adapters/upstox/feed_authorizer.py)
- [x] WS uses authorized URL on connect/reconnect — [`streaming.py`](brokers/adapters/upstox/streaming.py)
- [x] Callable token provider + `update_access_token` on refresh
- [x] Cancel post-verification with `ALREADY_EXECUTED` — [`orders.py`](brokers/adapters/upstox/orders.py)
- [x] `try_refresh_on_401` wired to HTTP client — [`gateway.py`](brokers/adapters/upstox/gateway.py)
- [x] `analytics_only` enforcement on orders

## Layer 1 — Behavioral Parity (Complete)

- [x] `complete.json.gz` instrument loader — [`instrument_loader.py`](brokers/adapters/upstox/instrument_loader.py)
- [x] Order idempotency via correlation ID
- [x] `OrderResponse.fail` for blocked orders (archive contract)
- [x] Index-aware instrument keys via `brokers/config/indices.py`
- [x] `gateway.load_instruments()` on startup option

## Layer 2 — Features (Complete)

- [x] Option chain — [`options.py`](brokers/adapters/upstox/options.py)
- [x] GTT place/modify/cancel — [`gtt.py`](brokers/adapters/upstox/gtt.py)
- [x] Extended APIs (profile, IPO, MF) — [`extended.py`](brokers/adapters/upstox/extended.py)
- [x] Portfolio stream — [`portfolio_stream.py`](brokers/adapters/upstox/portfolio_stream.py)
- [x] Batch LTP/quote — [`market_data.py`](brokers/adapters/upstox/market_data.py)
- [x] V3 intraday historical — [`historical.py`](brokers/adapters/upstox/historical.py)

## Tests

- 92 passing Upstox tests (unit + integration)
- Live WS parity gate: `brokers/tests/integration/test_upstox_ws_parity.py`
- Traceability matrix: [`review/UPSTOX_TEST_TRACEABILITY_MATRIX.md`](review/UPSTOX_TEST_TRACEABILITY_MATRIX.md)

## Remaining for Production

- Live integration tests for options/extended/latency (require market hours + credentials)
- 24h soak demonstration
- Prometheus metrics export
