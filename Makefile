PYTHON ?= python
.PHONY: bootstrap dev seed reset lint typecheck test e2e openapi synth eval eval-packbuilder eval-redteam report build deploy-dev deploy-prod preflight rollback clean
bootstrap dev seed reset lint typecheck test e2e openapi synth eval eval-packbuilder eval-redteam report build deploy-dev deploy-prod preflight rollback clean:
	$(PYTHON) scripts/tasks.py $@ $(if $(SERVICE),--service $(SERVICE),)
