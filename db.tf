resource "azurerm_postgresql_flexible_server" "postgres_server" {
  name                   = "openrouter-pg-server-${random_string.unique.result}"
  resource_group_name    = azurerm_resource_group.rg.name
  location               = "canadacentral"
  version                = "16"
  administrator_login    = var.postgres_admin_login
  administrator_password = var.postgres_admin_password
  storage_mb             = 32768
  sku_name               = "B_Standard_B1ms"

  zone = "1"
}

resource "azurerm_postgresql_flexible_server_database" "appdb" {
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.postgres_server.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_all" {
  name             = "allow-all-ips"
  server_id        = azurerm_postgresql_flexible_server.postgres_server.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "255.255.255.255"
}

output "postgresql_server_host" {
  value = azurerm_postgresql_flexible_server.postgres_server.fqdn
}
