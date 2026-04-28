resource "azurerm_cognitive_deployment" "msfoundry_chat_deployment_model" {
  name                 = "gpt-4.1-mini"
  cognitive_account_id = azapi_resource.ms_foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 100
  }

  model {
    format  = "OpenAI"
    name    = "gpt-4.1-mini"
    version = "2025-04-14"
  }
  version_upgrade_option = "OnceNewDefaultVersionAvailable"
  rai_policy_name        = "Microsoft.DefaultV2"

  depends_on = [
    azapi_resource.ms_foundry
  ]
}

resource "azurerm_cognitive_deployment" "msfoundry_chat_deployment_model_advanced" {
  name                 = "gpt-5.1"
  cognitive_account_id = azapi_resource.ms_foundry.id

  sku {
    name     = "GlobalStandard"
    capacity = 200
  }

  model {
    format  = "OpenAI"
    name    = "gpt-5.1"
    version = "2025-11-13"
  }
  version_upgrade_option = "OnceNewDefaultVersionAvailable"
  rai_policy_name        = "Microsoft.DefaultV2"

  depends_on = [
    azapi_resource.ms_foundry
  ]
}
