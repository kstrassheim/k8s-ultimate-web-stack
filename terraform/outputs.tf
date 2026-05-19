output "env" {
  value = var.env
}

output "app_name" {
  value = var.app_name
}

output "client_id" {
  description = "The Client ID for logon"
  value       = azuread_application.reg.client_id
}

output "tenant_id" {
  description = "The Tenant for the logon"
  value       = azuread_service_principal.enterprise.application_tenant_id
}

output "oauth2_permission_scope_uri" {
  description = "The full URI for the defined OAuth2 permission scope"
  value       = "api://${azuread_application.reg.client_id}/${tolist(azuread_application.reg.api[0].oauth2_permission_scope)[0].value}"
}

output "oauth2_permission_scope" {
  description = "The OAuth2 permission scope"
  value       = tolist(azuread_application.reg.api[0].oauth2_permission_scope)[0].value
}
