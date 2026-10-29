PYTHON ?= python3

.PHONY: check check-upstream
check:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -p 'test_astock_*.py' -v

check-upstream:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
