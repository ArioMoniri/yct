# YCT pipeline. Each phase target will write outputs/runs/<run_id>/ (v2.md §3 Provenance).
PY ?= python
# Base ref for range guards; CI passes origin/<PR base or default branch>.
BASE ?= $(shell git rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null || echo HEAD)

GUARDS = check_append_only check_prereg check_frozen_config check_human_signed check_blinding check_test_weakening

.PHONY: test lint guards all curate normalize transcribe tribe features stats predict report

test:
	$(PY) -m pytest -q

lint:
	ruff check .

guards:
	@fail=0; for g in $(GUARDS); do \
	  echo "== $$g (base $(BASE))"; \
	  $(PY) scripts/$$g.py --base $(BASE) || fail=1; \
	done; exit $$fail

all: curate normalize transcribe tribe features stats predict report

curate:
	@echo "TODO P1"
normalize:
	@echo "TODO P2"
transcribe:
	@echo "TODO P2b"
tribe:
	@echo "TODO P4"
features:
	@echo "TODO P5"
stats:
	@echo "TODO P7"
predict:
	@echo "TODO P8"
report:
	@echo "TODO P10"
