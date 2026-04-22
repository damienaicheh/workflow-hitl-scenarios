resource "azurerm_container_registry" "this" {
  name                = format("cr%s", local.resource_suffix_lowercase)
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  sku                 = "Basic"
  admin_enabled       = false

  tags = local.tags
}

resource "azapi_resource" "conn_acr" {
  type                      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name                      = azurerm_container_registry.this.name
  parent_id                 = azapi_resource.ms_foundry_project.id
  schema_validation_enabled = false

  depends_on = [
    azapi_resource.ms_foundry_project
  ]

  body = {
    name = azurerm_container_registry.this.name
    properties = {
      category = "ContainerRegistry"
      target   = azurerm_container_registry.this.login_server
      authType = "AAD"
      metadata = {
        ApiType    = "Azure"
        ResourceId = azurerm_container_registry.this.id
        location   = local.resource_group_location
      }
    }
  }
}
