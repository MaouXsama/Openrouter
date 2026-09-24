data "azurerm_client_config" "current" {}

resource "azurerm_user_assigned_identity" "app" {
  name                = "openrouter-identity-${random_string.unique.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
}

resource "azurerm_key_vault" "app" {
  name                = "openrouter-kv-${random_string.unique.result}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  tenant_id           = data.azurerm_client_config.current.tenant_id
  sku_name            = "standard"

  enable_rbac_authorization  = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = true
}

output "key_vault_name" {
  description = "Name of the Azure Key Vault used by the application"
  value       = azurerm_key_vault.app.name
}

resource "azurerm_role_assignment" "vm_key_vault_secrets_user" {
  scope                = azurerm_key_vault.app.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "deployment_key_vault_secrets_officer" {
  scope                = azurerm_key_vault.app.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

output "managed_identity_client_id" {
  description = "Client ID used by the application to authenticate with Azure"
  value       = azurerm_user_assigned_identity.app.client_id
}