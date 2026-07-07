# Makefile — project top-level entry points.
#
# Targets:
#   help                  show this help
#   verify-cassettes      6-grep VCR.py cassette secrets gauntlet
#   dhan-smoke            Tier-1 Dhan sandbox sanity check (RELIANCE LTP)
#   dhan-live-feed        Tier-2 Dhan WS market feed: prints live ticks for ~10s
#   dhan-prod-reads       Tier-3 Dhan prod-cred REST+WS reads with latency budgets (operator-gated)
#   certify-broker        Tier-3 6-area prod-cred broker certification (operator-gated)
#   test                  full test suite (skips @pytest.mark.live by default)
#   test-routing          run only the wiring + cassette tests
#   mypy                  mypy strict on touched modules
#
# Convention: each target is .PHONY, accepts no arguments, delegates to a
# real script or pytest invocation. This file is intentionally small —
# complex logic lives in scripts/ so it can be re-used by hooks / CI.
#
# Tier-3 (prod-cred) targets require:
#   export I_AM_RUNNING_PROD_READS=1
#   export DHAN_CLIENT_ID=…
#   export DHAN_ACCESS_TOKEN=…
# Plus gateway auto-blocks any /orders POST via allow_live_orders=False
# hard-coded in scripts/dhan_prod_reads.py and scripts/certify_broker.py.

.PHONY: help verify-cassettes dhan-smoke dhan-live-feed dhan-prod-reads certify-broker test test-routing mypy

help: ## show this help
	@awk 'BEGIN {FS = ":.*?## "}; /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}' \
		$(MAKEFILE_LIST)

verify-cassettes: ## run the YAML-aware secrets gauntlet against all VCR.py cassettes
	@python scripts/verify_cassettes.py

dhan-smoke: ## Tier-1 Dhan sandbox pre-flight: get LTP for RELIANCE; allow_live_orders=False
	@python scripts/dhan_smoke.py

dhan-live-feed: ## Tier-2 Dhan WS feed: prints live ticks for RELIANCE+NIFTY via the gateway
	@python scripts/dhan_live_feed.py

dhan-prod-reads: ## Tier-3 Dhan prod-cred REST+WS reads, latency-budgeted, allow_live_orders=False
	@python scripts/dhan_prod_reads.py

certify-broker: ## Tier-3 6-area prod-cred broker cert (Authentication/Resolution/MarketData/Portfolio/Latency/Reconnect-SKIP)
	@python scripts/certify_broker.py dhan

test: ## full project test suite (excludes @pytest.mark.live)
	@python -m pytest brokers/ --tb=short -q

test-routing: ## wiring + cassette tests under brokers/tests/integration
	@python -m pytest -m live \
		brokers/tests/integration/ \
		brokers/tests/test_risk_wiring_bootstrap.py \
		-v --tb=short

mypy: ## mypy strict on core module set
	@mypy \
		brokers/domain/ \
		brokers/provider/ \
		brokers/broker.py \
		brokers/risk.py \
		brokers/infrastructure/ \
		brokers/common/ \
		brokers/dhan/dhan_provider.py \
		brokers/upstox/upstox_provider.py \
		brokers/paper/paper_provider.py \
		brokers/tests/_live_modes.py \
		brokers/tests/conftest.py \
		brokers/tests/integration/test_dhan_live_market_data.py \
		--ignore-missing-imports --no-error-summary
