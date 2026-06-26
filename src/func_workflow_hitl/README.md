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

## Human-in-the-loop email notification

The pipeline is `input_router → drafter → reviewer (HITL pause) → publisher`, with a
`notify_executor` branch off the reviewer. When the reviewer pauses for approval it
emails the human a direct approve/reject link, so they no longer have to poll the
status endpoint and copy the instance id and request id by hand.

How it works:

- `reviewer_executor` calls `ctx.request_info(...)` to pause, then reads the id that
  call generated with `WorkflowHitlContext.pending_request_id(ctx)` and sends it to
  `notify_executor`.
- `notify_executor` builds the respond URL with `WorkflowHitlContext.from_context(ctx)`
  and emails it through Azure Communication Services (`AcsEmailTools`). The reviewer
  POSTs `{ "approved": true/false, "feedback": "..." }` to that URL to resume the run.

Why it is structured this way:

- The id is read straight back from the context, so nothing generates an id by hand.
  This is read immediately after `request_info`, which is reliable on the durable host
  because each executor runs in its own activity with its own runner context.
- The email is sent from a separate downstream executor, so a retried reviewer never
  emails a dead link, only the committed attempt's id reaches the notifier.

Requirements:

- The respond URL needs the function app host. `WEBSITE_HOSTNAME` is set automatically
  in Azure. The notifier skips the email (and logs a warning) when it is unset, for
  example during local `func start`, so the workflow still runs and you can approve via
  the status endpoint. For a custom domain or API Management gateway, pass
  `base_url=...` to `WorkflowHitlContext.from_context`.
- Reuses the existing `ACS_EMAIL_CONNECTION_STRING`, `ACS_EMAIL_SENDER`, and
  `ACS_RECIPIENT_EMAIL` settings.

This relies on the `WorkflowHitlContext` helper from the agent-framework branch pinned
in `requirements.txt` (see microsoft/agent-framework PR
`ahmedmuhsin:feature/python-durabletask-workflow-hitl-context`). The workflow is named
`iac_deployment`, so its routes are `workflow/iac_deployment/run`,
`workflow/iac_deployment/status/{instanceId}`, and
`workflow/iac_deployment/respond/{instanceId}/{requestId}`.
