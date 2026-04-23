# IaC Deployment Assistant — Workflow HITL Scenarios

Multi-agent Human-in-the-Loop (HITL) workflow that turns natural-language
infrastructure requests into validated Terraform code, pushed as a PR to
Azure DevOps. Built with [Microsoft Agent Framework](https://github.com/microsoft/agent-framework).

## Two deployment modes

| Mode | Entry point | Runtime | HITL mechanism |
|------|------------|---------|----------------|
| **Console** | `src/main.py` | Local (asyncio) | `input()` in terminal |
| **Azure Function** | `src/func_workflow_hitl/` | Durable Functions | `request_info` / `response_handler` |

Both share the same `config.py`, prompt files (`src/prompts/`), and tool
implementations.

## Architecture

```
                  ┌──────────────────────────────────────┐
                  │  Phase 1 — iterative review loop     │
                  │                                      │
   User request ──▶  drafter ─▶ validator ─▶ reviewer    │
                  │     ▲                       │        │
                  │     └── human feedback ◀────┘        │
                  └──────────────┬───────────────────────┘
                                 │ approve
                  ┌──────────────▼───────────────────────┐
                  │  Phase 2 — deployment (runs once)    │
                  │                                      │
                  │  publisher ─▶ notifier ─▶ deployer   │
                  │                             │        │
                  │                          reporter    │
                  └──────────────────────────────────────┘
```

## Quick start

```bash
cd src
cp .env.template .env   # fill in your values
uv sync
az login
```

### Console HITL workflow

```bash
uv run main.py
```

### DevUI (single agent)

```bash
uv run ado_agent.py     # http://localhost:8090
```

### Azure Function (serverless HITL)

```bash
cd func_workflow_hitl
cp local.settings.json.template local.settings.json
# fill in values, then:
azurite --silent --location .   # local storage emulator
func start
```

See `func_workflow_hitl/demo.http` for sample requests.

## Project structure

```
src/
├── config.py                   # Shared config (env, clients, MCP, prompt loader)
├── main.py                     # Console HITL workflow (two-phase)
├── ado_agent.py                # DevUI single-agent on port 8090
├── prompts/                    # Externalized agent instructions
│   ├── drafter.txt
│   ├── validator.txt
│   ├── reviewer.txt
│   ├── publisher.txt
│   ├── notifier.txt
│   ├── deployer.txt
│   ├── reporter.txt
│   └── ado_agent.txt
├── tools/
│   ├── azure_devops_tools.py   # Git push, PR creation (REST API)
│   ├── terraform_tools.py      # validate / fmt via CLI
│   ├── pipeline_tools.py       # ADO pipeline monitoring
│   ├── teams_tools.py          # Adaptive Cards via webhook
│   └── email_tools.py          # Email via Azure Comm Services
└── func_workflow_hitl/          # Azure Function deployment
    ├── function_app.py          # AgentFunctionApp entry point
    ├── executors/               # WorkflowBuilder executors (Damien's pattern)
    ├── models/                  # HITL request/response dataclasses
    └── utils/                   # Response extraction helpers
```

## Infrastructure

Terraform files in `infra/` provision the backing Azure resources
(AI Foundry project, model deployments, ACS, etc.):

```bash
cd infra
az login --use-device-code
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
terraform init
terraform plan -out plan.out
terraform apply plan.out
```

## Environment variables

See `.env.template` for the full list. Key variables:

| Variable | Required | Used by |
|----------|----------|---------|
| `FOUNDRY_PROJECT_ENDPOINT` | Yes | All |
| `FOUNDRY_DEFAULT_MODEL` | Yes | All |
| `ADO_ORG` | Yes | Console, DevUI |
| `ADO_PAT` | Yes | Console, DevUI |
| `TEAMS_WEBHOOK_URL` | No | Console (notifier/reporter) |
| `ACS_CONNECTION_STRING` | No | Email notifications |