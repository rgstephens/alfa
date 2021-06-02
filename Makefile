SRC := alfa
TMP := tmp
PYTEST := `which py.test`
MYPY_REPORT := $(CURDIR)/$(TMP)/mypy
TESTS_REPORT := $(CURDIR)/$(TMP)/tests
HTMLCOV := $(TESTS_REPORT)/htmlcov

clean:
	find . -type f -name "*py[co]" -delete
	find . -type d -name "__pycache__" -delete


# REQUIREMENTS
install-pip:
	pip install pip==21.0.1
	pip install poetry==1.1.4

sync-requirements: install-pip
	poetry install

update-requirements: install-pip
	poetry update

requirements: update-requirements sync-requirements


# CICD: CHECKS
check-isort:
	./code_checks/make_isort.sh $(SRC)

check-black:
	./code_checks/make_black.sh $(SRC)

check-autoflake:
	./code_checks/make_autoflake.sh $(SRC)

check-format: check-autoflake check-black check-isort

check-mypy:
	rm -rf .mypy_cache
	rm -rf $(MYPY_REPORT)
	MYPYPATH="$(SRC)" \
		mypy --config-file=setup.cfg \
		--junit-xml=$(MYPY_REPORT)/mypy_junit_report.xml \
		--html-report=$(MYPY_REPORT)/mypy_html_report \
		.

# CODE: FORMAT
isort:
	./code_checks/make_isort.sh -f $(SRC)

black:
	./code_checks/make_black.sh -f $(SRC)

autoflake:
	./code_checks/make_autoflake.sh -f $(SRC)

format: autoflake black isort

# RUN
run-server:
	python alfa/example/main.py

docker-run:
	docker-compose -f docker-compose.yml up -d --build

# TESTS
tests:
	cd $(SRC) && \
		mkdir -p $(TESTS_REPORT) && \
		export COVERAGE_FILE=$(TESTS_REPORT)/coverage.cov && \
			$(PYTEST) . \
			--cov alfa --cov-report term-missing --cov-config=../setup.cfg --cov-report=

coverage-combine:
	coverage combine $(TESTS_REPORT)/*.cov

coverage-report: coverage-combine
	coverage report

coverage-html-report: coverage-combine
	coverage html -d $(HTMLCOV)


check: clean requirements format check-mypy tests
