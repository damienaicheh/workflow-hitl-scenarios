# POC – IaC Deployment Assistant

Multi-agent HITL (Human-in-the-Loop) workflow that automates Azure IaC deployments end-to-end.

## Architecture

```
User request
    │
    ▼
┌──────────┐   ┌───────────┐   ┌───────────┐   ┌──────────┐
│ drafter  │──▶│ validator │──▶│ publisher │──▶│ notifier │
└──────────┘   └───────────┘   └───────────┘   └──────────┘
                                                     │
                                               ┌─────┴─────┐
                                               │  HUMAN    │
                                               │  REVIEW   │
                                               └─────┬─────┘
                                                     │
                                                ┌────┴────┐   ┌──────────┐
                                                │deployer │──▶│ reporter │
                                                └─────────┘   └──────────┘
```

## Agents

| Agent      | Role                                       | Tools                                          |
|------------|--------------------------------------------|-------------------------------------------------|
| drafter    | Generate Terraform .tf files from request  | –                                               |
| validator  | Run `terraform validate` + `terraform fmt` | validate_terraform, format_terraform            |
| publisher  | Push to AzDO branch + create PR            | MCP AzDO, push_terraform_branch, create_pull_request |
| notifier   | Send Teams Adaptive Card + summary         | send_teams_approval_card                        |
| deployer   | Monitor pipeline run                       | get_pipeline_runs, get_pipeline_run_status      |
| reporter   | Final summary + Teams status card          | send_teams_status_card                          |

## Setup

```bash
cd src
cp .env.template .env
# Fill in the .env values
uv sync
```

## Run – Console HITL workflow

```bash
uv run main.py
```

## Run – DevUI (single agent)

```bash
uv run ado_agent.py
```

## Infrastructure

Terraform files in `infra/` provision the Azure resources (AI Foundry, models, ACS, etc.).
