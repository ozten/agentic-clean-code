# Harness entry points. Paid commands (qualify, run) require an explicit manifest
# with batch_usd_cap and a passing preflight; ordinary tests make no network calls.
UV ?= uv
HARNESS = $(UV) run python -B -m harness.cli
export PYTHONPATH := benchmarks/troubleshooting

.PHONY: sync preflight test test-examples test-harness parity leak-check packages estimate qualify pilot status cancel grade analyze

sync:
	$(UV) sync --frozen

preflight:
	$(HARNESS) preflight

test: test-examples test-harness

test-examples:
	python3 -B -m unittest discover -s examples/contractor-payment -v
	python3 -B -m unittest discover -s benchmarks/troubleshooting -p 'test_comparison.py' -v

test-harness:
	$(UV) run python -B -m unittest discover -s benchmarks/troubleshooting/tests -t benchmarks/troubleshooting -v

parity:
	$(HARNESS) parity

leak-check:
	$(HARNESS) leak-check

packages:
	$(HARNESS) build-packages

estimate:
	$(HARNESS) estimate --manifest $(MANIFEST)

qualify:
	$(HARNESS) qualify --manifest $(MANIFEST)

pilot:
	$(HARNESS) run --manifest $(MANIFEST)

status:
	$(HARNESS) status --run $(RUN)

cancel:
	$(HARNESS) cancel --run $(RUN)

grade:
	$(HARNESS) grade --run $(RUN)

analyze:
	$(HARNESS) analyze --run $(RUN)
