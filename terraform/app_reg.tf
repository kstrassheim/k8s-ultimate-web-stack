resource "azuread_application" "reg" {
  display_name     = var.env == "prod" ? var.app_name : "${var.app_name}-${var.env}"
  sign_in_audience = "AzureADMyOrg"

  # Per-env app icon (dev / test / prod each have a distinct logo).
  logo_image = filebase64("${path.module}/../frontend/logo_src/${var.env}/logo.png")

  api {
    mapped_claims_enabled          = true
    requested_access_token_version = 2

    oauth2_permission_scope {
      admin_consent_description  = "Allow the application to access the backend on behalf of the signed-in user."
      admin_consent_display_name = "Backend Access"
      enabled                    = true
      id                         = "96183846-204b-4b43-82e1-5d2222eb4b9b"
      type                       = "User"
      user_consent_description   = "Allow the application to access backend on your behalf."
      user_consent_display_name  = "Backend Access"
      value                      = "user_impersonation"
    }
  }

  app_role {
    allowed_member_types = ["User", "Application"]
    description          = "Admins can manage roles and perform all task actions"
    display_name         = "Admin"
    enabled              = true
    id                   = "1b19509b-32b1-4e9f-b71d-4992aa991967"
    value                = "admin"
  }

  app_role {
    allowed_member_types = ["User"]
    description          = "ReadOnly roles have limited query access"
    display_name         = "ReadOnly"
    enabled              = true
    id                   = "497406e4-012a-4267-bf18-45a1cb148a01"
    value                = "User"
  }

  single_page_application {
    # The app is reachable at two mounts per env: the internal nginx subpath
    # (datapi.galaxus.box/ultimate-web-stack*) and the Cloudflare tunnel root
    # (*.futuristic.science). redirectUri is origin+basePath, so both must be
    # registered.
    redirect_uris = (
      var.env == "dev"
      ? [
        "https://datapi.galaxus.box/ultimate-web-stack-dev/",
        "https://ultimate-web-stack-dev.futuristic.science/",
        "http://localhost:8000/",
        "http://localhost:5173/",
      ]
      : var.env == "test"
      ? [
        "https://datapi.galaxus.box/ultimate-web-stack-test/",
        "https://ultimate-web-stack-test.futuristic.science/",
      ]
      : [
        "https://datapi.galaxus.box/ultimate-web-stack/",
        "https://ultimate-web-stack.futuristic.science/",
      ]
    )
  }

  # Microsoft Graph delegated permissions the SPA uses (User.Read for /me + photo,
  # Group.Read.All for /groups). Appears under "Configured permissions"; still
  # needs admin consent ("Grant admin consent") to be effective.
  required_resource_access {
    resource_app_id = "00000003-0000-0000-c000-000000000000" # Microsoft Graph

    resource_access {
      id   = "e1fe6dd8-ba31-4d61-89e7-88639da4683d" # User.Read (delegated)
      type = "Scope"
    }
    resource_access {
      id   = "5f8c59db-677d-491f-a6b8-5f174b11ec1d" # Group.Read.All (delegated)
      type = "Scope"
    }
  }

  lifecycle {
    ignore_changes = [identifier_uris]
  }
}

resource "azuread_service_principal" "enterprise" {
  client_id                    = azuread_application.reg.client_id
  app_role_assignment_required = true
}

# Application ID URI (api://<client_id>) so the SPA can request the API scope
# api://<client_id>/user_impersonation. Managed separately because the app
# resource ignores identifier_uris changes (the URI references the client_id,
# which only exists after creation).
resource "azuread_application_identifier_uri" "api" {
  application_id = azuread_application.reg.id
  identifier_uri = "api://${azuread_application.reg.client_id}"
}