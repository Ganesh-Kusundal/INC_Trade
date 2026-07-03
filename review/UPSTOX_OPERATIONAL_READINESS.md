# Upstox Operational Readiness Assessment

**Date:** 2026-07-03  
**Verdict:** CONDITIONALLY READY FOR STAGING

## Production Readiness Checklist (Re-Score)

| Category | Status | Notes |
|----------|--------|-------|
| Authentication | Ready | 6 modes, PKCE, TOTP scheduler, concurrent refresh lock |
| Token lifecycle | Ready | `try_refresh_on_401` wired; WS token propagation via `on_token_change` |
| Instrument master | Ready | `complete.json.gz` loader with 24h cache; `load_instruments()` on gateway |
| Orders | Ready | Idempotency, analytics guard, cancel fill-race verification |
| Market data REST | Ready | LTP/quote/depth + batch methods |
| Streaming | Ready | Feed authorizer + authorized WS URL on connect/reconnect |
| Historical | Partial | V2 + V3 intraday; empty list on failure (archive parity) |
| Portfolio stream | Ready | Portfolio WS authorizer wired |
| GTT | Partial | Place/modify/cancel implemented; no list-all (API limitation) |
| Observability | Partial | `UpstoxMetrics` counters; no Prometheus export yet |
| Test parity | Partial | 73+ unit tests; live WS parity gate ported |
| Soak / DR | Not demonstrated | Requires 24h soak run in staging |

## Metrics

`UpstoxGateway.metrics` exposes:
- `refresh_count`, `error_count`, `ws_connected`, `ws_reconnects`

## Performance Benchmarks

Port `archive/.../test_endpoint_latency.py` thresholds to staging CI:
- quote < 2s, ltp < 1s, depth < 2s, funds < 2s

## Staging Exit Criteria

1. `PRE_PROD_GATE=1` WS parity tests pass during market hours
2. `brokers/scripts/upstox_live_parity_compare.py` returns exit 0
3. 24h soak with TOTP refresh + WS reconnect without manual intervention
4. Zero Critical/High open items from parity audit

## Remaining Before Production

- Live integration suite for options chain, extended APIs, endpoint latency
- Prometheus metrics export
- Full `UpstoxBrokerGateway` flat API compatibility shim (if legacy consumers exist)
