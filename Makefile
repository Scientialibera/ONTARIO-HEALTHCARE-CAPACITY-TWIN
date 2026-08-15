.PHONY: install dev test run docker

install:
	python -m pip install -e ".[dev]"

run:
	uvicorn api.main:app --reload

test:
	pytest

docker:
	docker build -t ontario-healthcare-capacity-twin .
