PYTHON ?= python3

.PHONY: check check-upstream build
check:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_astock_*.py' -v

check-upstream:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v

DIST_DIR ?= dist
build:
	$(PYTHON) -m build --no-isolation --outdir "$(DIST_DIR)"
