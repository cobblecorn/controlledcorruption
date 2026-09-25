.PHONY: install dev test lint demo gui clean

install:
	pip install -e .

dev:
	pip install -e '.[dev,gui,yaml]'

test:
	python -m pytest -q

# GUI tests need an offscreen Qt platform in headless environments.
test-all:
	QT_QPA_PLATFORM=offscreen python -m pytest -q

lint:
	ruff check src tests

demo:
	python -m controlled_corruptor.cli.main demo demo.z64
	python -m controlled_corruptor.cli.main info demo.z64

gui:
	python -m controlled_corruptor.ui.app

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .ruff_cache
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
