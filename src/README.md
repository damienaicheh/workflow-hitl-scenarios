# IaC Deployment Assistant

Multi-agent HITL (Human-in-the-Loop) workflow that turns natural-language
infrastructure requests into validated Terraform code, pushed as a PR to
Azure DevOps.

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

The key differentiator is the **iterative review loop**: the human can
request changes up to 5 times, and each round re-drafts the Terraform
incorporating **all** accumulated feedback — not just the latest.

## Agents

| Agent       | Phase | Role                                            | Tools                                                |
|-------------|-------|-------------------------------------------------|------------------------------------------------------|
| **drafter** | 1     | Generate `.tf` files from natural language       | —                                                    |
| **validator** | 1   | Run `terraform validate` + `terraform fmt`       | `validate_terraform`, `format_terraform`             |
| **reviewer** | 1    | Present human-readable summary, collect feedback | —                                                    |
| **publisher** | 2   | Push branch + create PR on Azure DevOps          | MCP ADO, `push_terraform_branch`, `create_pull_request` |
| **notifier** | 2    | Send Teams Adaptive Card with PR link            | `send_teams_approval_card`                           |
| **deployer** | 2    | Monitor CI/CD pipeline run                       | `get_pipeline_runs`, `get_pipeline_run_status`       |
| **reporter** | 2    | Final summary + Teams status card                | `send_teams_status_card`                             |

## Project structure

```
src/
├── config.py                   # Shared configuration (env, clients, MCP, prompt loader)
├── main.py                     # Console HITL workflow (two-phase)
├── ado_agent.py                # DevUI single-agent on port 8090
├── pyproject.toml
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
│   ├── azure_devops_tools.py   # Git push, PR creation
│   ├── terraform_tools.py      # validate / fmt via CLI
│   ├── pipeline_tools.py       # ADO pipeline monitoring
│   ├── teams_tools.py          # Adaptive Cards via webhook
│   └── email_tools.py          # Email via Azure Comm Services
└── func_workflow_hitl/          # Azure Function serverless HITL
    ├── function_app.py          # AgentFunctionApp (uses config.py)
    ├── executors/               # WorkflowBuilder executors
    ├── models/                  # HITL request/response dataclasses
    └── utils/                   # Response extraction helpers
```

## Setup

```bash
cd src
cp .env.template .env
# Fill in the values (see .env.template for details)
uv sync
az login
```

## Run — console HITL workflow

```bash
uv run main.py
```

## Run — DevUI (single agent)

```bash
uv run ado_agent.py
# Open http://localhost:8090
```

## Infrastructure

Terraform files in `infra/` provision the backing Azure resources
(AI Foundry project, model deployments, ACS, etc.).
