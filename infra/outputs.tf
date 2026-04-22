output "resource_group_name" {
  value = local.resource_group_name
}

output "foundry_endpoint" {
  value = "https://${format("aif-%s", local.resource_suffix_kebabcase)}.services.ai.azure.com/api/projects/${azapi_resource.ms_foundry_project.name}"
}

output "acs_name" {
  value = azurerm_communication_service.this.name
}

output "cosmos_db_endpoint" {
  value = azurerm_cosmosdb_account.this.endpoint
}
