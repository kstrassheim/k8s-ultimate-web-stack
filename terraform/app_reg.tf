resource "azuread_application" "reg" {
  display_name     = var.env == "prod" ? var.app_name : "${var.app_name}-${var.env}"
  sign_in_audience = "AzureADMyOrg"

  api {
    mapped_claims_enabled          = true
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allow the application to access the backend on behalf of the signed-in user."
      admin_consent_display_name   = "Backend Access"
      enabled                     = true
      id                          = "96183846-204b-4b43-82e1-5d2222eb4b9b"
      type                        = "User"
      user_consent_description    = "Allow the application to access backend on your behalf."
      user_consent_display_name   = "Backend Access"
      value                       = "user_impersonation"
    }
  }

  app_role {
    allowed_member_types = ["User", "Application"]
    description          = "Admins can manage roles and perform all task actions"
    display_name        = "Admin"
    enabled             = true
    id                  = "1b19509b-32b1-4e9f-b71d-4992aa991967"
    value               = "admin"
  }

  app_role {
    allowed_member_types = ["User"]
    description          = "ReadOnly roles have limited query access"
    display_name        = "ReadOnly"
    enabled             = true
    id                  = "497406e4-012a-4267-bf18-45a1cb148a01"
    value               = "User"
  }

  single_page_application {
    redirect_uris = var.env == "dev"
      ? ["http://localhost:8000/", "http://localhost:5173/"]
      : []
  }

  lifecycle {
    ignore_changes = [identifier_uris]
  }
}

resource "azuread_service_principal" "enterprise" {
  client_id                   = azuread_application.reg.client_id
  app_role_assignment_required = true
}

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