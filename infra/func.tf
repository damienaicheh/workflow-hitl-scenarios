resource "azurerm_function_app_flex_consumption" "this" {
  name                = format("func-%s", local.resource_suffix_kebabcase)
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  service_plan_id     = azurerm_service_plan.func_flex.id

  storage_container_type      = "blobContainer"
  storage_container_endpoint  = "${azurerm_storage_account.func_flex.primary_blob_endpoint}${azurerm_storage_container.func_flex_container.name}"
  storage_authentication_type = "UserAssignedIdentity"

  storage_user_assigned_identity_id = azurerm_user_assigned_identity.function_identity.id
  runtime_name                      = "python"
  runtime_version                   = "3.13"
  maximum_instance_count            = 50
  instance_memory_in_mb             = 2048

  tags = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.function_identity.id]
  }

  app_settings = {
    "TASKHUB_NAME" : "WorkflowHitlHub",
    "FOUNDRY_PROJECT_ENDPOINT" : format("https://%s.services.ai.azure.com/api/projects/%s", azapi_resource.ms_foundry.name, azapi_resource.ms_foundry_project.name),
    "FOUNDRY_DEFAULT_MODEL" : azurerm_cognitive_deployment.msfoundry_chat_deployment_model.name,
    "FOUNDRY_ORCHESTRATOR_MODEL" : azurerm_cognitive_deployment.msfoundry_chat_deployment_model_advanced.name,
    "ADO_ORG" : "https://dev.azure.com/M365CPI49792204",
    "ADO_PAT" : "@Microsoft.KeyVault(SecretUri=${azurerm_key_vault_secret.ado_pat.versionless_id})",
    "ADO_DEFAULT_PROJECT" : "ai-scenario",
    "ADO_REPO" : "agent-framework-scenario",
    "ACS_EMAIL_CONNECTION_STRING" : azurerm_communication_service.this.primary_connection_string,
    "ACS_EMAIL_SENDER" : format("DoNotReply@%s", azurerm_email_communication_service_domain.this.mail_from_sender_domain),
    "ACS_RECIPIENT_EMAIL" : var.acs_recipient_email,
    "AZURE_CLIENT_ID" : azurerm_user_assigned_identity.function_identity.client_id,
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.this.connection_string
    AzureWebJobsStorage__clientId         = azurerm_user_assigned_identity.function_identity.client_id
    AzureWebJobsStorage__credential       = "managedidentity"
    AzureWebJobsStorage__accountName      = azurerm_storage_account.func_flex.name
    AzureWebJobsStorage__blobServiceUri   = format("https://%s.blob.core.windows.net/", azurerm_storage_account.func_flex.name)
    AzureWebJobsStorage__queueServiceUri  = format("https://%s.queue.core.windows.net/", azurerm_storage_account.func_flex.name)
    AzureWebJobsStorage__tableServiceUri  = format("https://%s.table.core.windows.net/", azurerm_storage_account.func_flex.name)
  }

  site_config {
    health_check_path                 = "/api/health"
    health_check_eviction_time_in_min = 2
  }
}

resource "azapi_update_resource" "function_app_key_vault_reference_identity" {
  type        = "Microsoft.Web/sites@2023-12-01"
  resource_id = azurerm_function_app_flex_consumption.this.id

  body = {
    properties = {
      keyVaultReferenceIdentity = azurerm_user_assigned_identity.function_identity.id
    }
  }

  depends_on = [
    azurerm_role_assignment.function_app_key_vault_secret_user,
  ]
}
