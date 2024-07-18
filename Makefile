help:
	@echo 'Individual commands:'
	@echo ' build            - Build the Transcoder Docker container'
	@echo ' up               - Start the Transcoder'
	@echo ' down             - Stop the Transcoder and remove the networks'
	@echo ' lint             - Lint the code with pylint and flake8 and check imports'
	@echo '                    have been sorted correctly'
	@echo ' test             - Run tests'
	@echo ''
	@echo 'Grouped commands:'
	@echo ' linttest         - Run lint and test'
build:
	docker-compose -f docker-compose-dev.yml up --build
up:
	docker-compose -f docker-compose-dev.yml up
down:
	docker-compose down
lint:
	# Lint the code and check imports have been sorted correctly
	pylint *
	flake8
	isort -rc --check-only .
test:
	# Run tests
	pytest -v -s app/tests.py
linttest: lint test
