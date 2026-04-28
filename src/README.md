# IaC Deployment Assistant

Multi-agent HITL (Human-in-the-Loop) workflow that turns natural-language
infrastructure requests into validated Terraform code, pushed as a PR to
Azure DevOps.


## Setup

```bash
az login
```

```bash
cd src/func_workflow_hitl
cp .env.template .env
# Fill in the values (see .env.template for details)

# Install Python dependencies
pip install -r requirements.txt

# Start the Azure Functions runtime
func start
```
