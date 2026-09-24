resource "azurerm_storage_account" "storage" {
  name                     = "openrouterstorage${random_string.unique.result}"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = "canadacentral" # <--- نقل حساب التخزين أيضاً ليكون بجانب قاعدة البيانات في كندا
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_container" "container" {
  name                  = "pdf-container"
  storage_account_name  = azurerm_storage_account.storage.name
  container_access_type = "private"
}

resource "random_string" "unique" {
  length  = 6
  special = false
  upper   = false
}

output "azure_storage_account_name" {
  value = azurerm_storage_account.storage.name
}

output "azure_storage_container_name" {
  value = azurerm_storage_container.container.name
}
