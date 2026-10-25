PYTHON ?= python3
.PHONY: install test lint format schema check dist zip

install:
	$(PYTHON) -m pip install -e '.[dev,browser,publish]'

test:
	$(PYTHON) -m unittest discover -s tests -v
	node --test tests/*.test.cjs

lint:
	$(PYTHON) -m ruff check src tests tools
	$(PYTHON) -m ruff format --check src tests tools

format:
	$(PYTHON) -m ruff check --fix src tests tools
	$(PYTHON) -m ruff format src tests tools

schema:
	$(PYTHON) tools/export_schema.py

check: lint test
	$(PYTHON) tools/export_schema.py --check

dist:
	$(PYTHON) -m build
	$(PYTHON) -m twine check dist/*.whl dist/*.tar.gz
	$(PYTHON) tools/check_dist.py

# Source archives use the same explicit file selection as release builds.
zip: dist
	$(PYTHON) tools/source_zip.py
