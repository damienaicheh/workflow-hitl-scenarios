resource "azurerm_service_plan" "func_flex" {
  name                = format("asp-func-%s", local.resource_suffix_kebabcase)
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  sku_name            = "FC1"
  os_type             = "Linux"
}