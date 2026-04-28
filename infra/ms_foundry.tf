resource "azapi_resource" "ms_foundry" {
  type                      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name                      = format("aif-%s", local.resource_suffix_kebabcase)
  parent_id                 = local.resource_group_id
  location                  = local.resource_group_location
  schema_validation_enabled = false
  tags                      = local.tags_azapi

  body = {
    kind = "AIServices",
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
      disableLocalAuth       = false
      allowProjectManagement = true
      customSubDomainName    = format("aif-%s", local.resource_suffix_kebabcase)
      publicNetworkAccess    = "Enabled"
      networkAcls = {
        defaultAction = "Allow"
      }
    }
  }

  response_export_values = [
    "identity.principalId",
  ]

  depends_on = [
    azurerm_user_assigned_identity.this
  ]
}

# Account-level capability host (must exist before project-level)
resource "azapi_resource" "ms_foundry_capability_host" {
  type                      = "Microsoft.CognitiveServices/accounts/capabilityHosts@2026-01-15-preview"
  name                      = format("cap-host-%s", local.resource_suffix_kebabcase)
  parent_id                 = azapi_resource.ms_foundry.id
  schema_validation_enabled = false

  body = {
    properties = {
      capabilityHostKind             = "Agents"
      enablePublicHostingEnvironment = true
    }
  }

  depends_on = [
    azapi_resource.ms_foundry
  ]
}
