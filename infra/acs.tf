resource "azurerm_communication_service" "this" {
  name                = format("acs-%s", local.resource_suffix_kebabcase)
  resource_group_name = local.resource_group_name
  data_location       = "France"
  tags                = local.tags
}

resource "azurerm_email_communication_service" "this" {
  name                = format("acs-email-%s", local.resource_suffix_kebabcase)
  resource_group_name = local.resource_group_name
  data_location       = "France"
}

resource "azurerm_email_communication_service_domain" "this" {
  name             = "AzureManagedDomain"
  email_service_id = azurerm_email_communication_service.this.id

  domain_management = "AzureManaged"
}

resource "azurerm_communication_service_email_domain_association" "this" {
  communication_service_id = azurerm_communication_service.this.id
  email_service_domain_id  = azurerm_email_communication_service_domain.this.id
}