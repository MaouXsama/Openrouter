variable "location" {
  type    = string
  default = "East US"
}
variable "postgres_admin_login" {
  type    = string
  default = "azureadmin"
}

variable "postgres_admin_password" {
  type      = string
  sensitive = true
}