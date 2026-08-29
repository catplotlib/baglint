# ROS installs put /opt/ros/*/site-packages on PYTHONPATH, which leaks into the
# venv and drags ROS's pytest plugins into our test run. baglint is deliberately
# ROS-free, so every target runs with PYTHONPATH cleared.
PY := .venv/bin/python
RUN := env -u PYTHONPATH

.PHONY: install test lint clean

install:
	python3 -m venv .venv
	$(RUN) $(PY) -m pip install -q --upgrade pip
	$(RUN) $(PY) -m pip install -q -e ".[dev]"

test:
	$(RUN) $(PY) -m pytest -q

clean:
	rm -rf .venv .pytest_cache **/__pycache__ *.egg-info
