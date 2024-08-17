.PHONY: run-dev, docker-shell, docker-build, docker-run, test, test-functions, test-watch-functions, cdk-deploy, cdk-synth, test, test-snapshot-update, lint, fix, lint-fix

DIRS = lib

test:
	pytest --cov --cov-branch --cov-report=xml --cov-report=term-missing:skip-covered --junitxml=.sonar/xunit-result.xml

test-functions:
	pytest --cov --cov-branch --cov-report=xml --cov-report=term-missing:skip-covered --junitxml=.sonar/xunit-result.xml tests/unit/functions

test-watch-functions:
	ptw cdk/functions/ tests/unit/functions -- tests/unit/functions --cov

test-snapshot-update:
	pytest --snapshot-update

lint:
	flake8 --statistics --tee --output-file=.sonar/flake8.rpt

fix:
	black --line-length 120 .
	autoflake -r --in-place --remove-unused-variables --remove-all-unused-imports --ignore-init-module-imports --remove-duplicate-keys .

lint-fix: fix lint

cdk-deploy:
	npx cdk deploy --all --require-approval never

cdk-synth:
	npx cdk list