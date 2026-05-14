variable "app_name" {}
variable "env" {
  default = "dev"
}

output "env" {
  value = var.env
}
output "app_name" {
  value = var.app_name
}
output "client_id" {
  value = azuread_application.reg.client_id
}
output "tenant_id" {
  value = azuread_service_principal.enterprise.application_tenant_id
}
output "oauth2_permission_scope_uri" {
  value = "api://${azuread_application.reg.client_id}/${tolist(azuread_application.reg.api[0].oauth2_permission_scope)[0].value}"
}
output "oauth2_permission_scope" {
  value = tolist(azuread_application.reg.api[0].oauth2_permission_scope)[0].value
}