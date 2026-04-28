# IaC Deployment Assistant

Multi-agent HITL (Human-in-the-Loop) workflow that turns natural-language
infrastructure requests into validated Terraform code, pushed as a PR to
Azure DevOps.

## Local setup

```bash
az login
```

```bash
cd src/func_workflow_hitl
cp local.settings.json.template local.settings.json
# Fill in the values (see local.settings.json.template for details)

# Install Python dependencies
pip install -r requirements.txt

# Start the Azure Functions runtime
func start
```

Deploy the Function App using the Azure CLI:

```bash
func azure functionapp publish <function_app_name>
```