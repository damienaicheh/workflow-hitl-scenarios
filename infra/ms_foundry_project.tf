resource "azapi_resource" "ms_foundry_project" {
  type                      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name                      = format("prj-%s", local.resource_suffix_kebabcase)
  parent_id                 = azapi_resource.ms_foundry.id
  location                  = local.resource_group_location
  schema_validation_enabled = false
  tags                      = local.tags_azapi

  body = {
    sku = {
      name = "S0"
    }
    identity = {
      type = "SystemAssigned, UserAssigned"
      userAssignedIdentities = {
        (azurerm_user_assigned_identity.this.id) = {}
      }
    }

    properties = {
      displayName = "project"
      description = "A project for the AI Foundry account with network secured deployed Agent using User Assigned Identity"
    }
  }

  response_export_values = [
    "identity.principalId",
    "properties.internalId"
  ]

  depends_on = [
    azapi_resource.ms_foundry,
  ]
}

resource "azapi_resource" "ms_foundry_project_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/capabilityHosts@2026-01-15-preview"
  name                      = format("prj-cap-host-%s", local.resource_suffix_kebabcase)
  parent_id                 = azapi_resource.ms_foundry_project.id
  schema_validation_enabled = false

  body = {
    properties = {
      vectorStoreConnections = [
        azapi_resource.ai_search.name
      ]
      storageConnections = [
        azurerm_storage_account.this.name
      ]
      threadStorageConnections = [
        azurerm_cosmosdb_account.this.name
      ]
    }
  }

  depends_on = [
    azapi_resource.ms_foundry_capability_host,
    azapi_resource.conn_ai_search,
    azapi_resource.conn_cosmos_db,
    azapi_resource.conn_storage,
    azurerm_role_assignment.cosmosdb_operator_uai,
    azurerm_role_assignment.storage_blob_data_contributor_uai,
    azurerm_role_assignment.search_index_data_contributor_uai,
    azurerm_role_assignment.search_service_contributor_uai,
  ]
}
