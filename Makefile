# YCT pipeline. Each phase target will write outputs/runs/<run_id>/ (v2.md §3 Provenance).
PY ?= python
# Base ref for range guards. Default EMPTY = the whole history from the first commit: a real, never-empty
# range (documented history exceptions live in config.yaml `guards:`). An explicit BASE whose range
# merge-base(BASE, HEAD)..HEAD is empty is refused, so a guard never prints OK having checked nothing
# (QA G-D032 D4).
BASE ?= EMPTY
RUN_ID ?= $@_$(shell date -u +%Y%m%dT%H%M%SZ)

GUARDS = check_append_only check_prereg check_frozen_config check_human_signed check_blinding check_test_weakening

.PHONY: test test-raw lint guards all curate normalize transcribe tribe features stats predict report

# Test claims need a run dir (v2.md §3 Provenance): outputs/runs/<run_id>/{cmd,git_sha,config_sha,...}.
test:
	$(PY) scripts/run_with_provenance.py --run-id $(RUN_ID) -- $(PY) -m pytest -q

test-raw:
	$(PY) -m pytest -q

lint:
	ruff check .

guards:
	@$(PY) scripts/guard_range.py --base $(BASE)
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
