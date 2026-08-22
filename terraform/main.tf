terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.8"
    }
  }
  # container_name and key come from variables rather than -backend-config flags.
  # This is OpenTofu early evaluation: they resolve at `tofu init`, before state
  # exists. HashiCorp Terraform cannot parse it -- moot, since the encryption
  # block below already makes this project OpenTofu-only.
  backend "azurerm" {
    resource_group_name  = "terraform"
    storage_account_name = "mytofustates"
    container_name       = var.app_name         # blob container == project name
    key                  = "${var.env}.tfstate" # dev/test/prod.tfstate
    use_azuread_auth     = true
  }

  # ---------------------------------------------------------------------------
  # State encryption. A per-run AES-GCM data key is wrapped by the RSA key
  # `k8s-ultimate-web-stack` in the kv-mytofustates Key Vault, so key material
  # never leaves the vault. dev, test and prod share that key; each keeps its
  # own state blob.
  #
  # use_oidc/use_cli/client_id/tenant_id must be block arguments -- this key
  # provider does NOT read ARM_USE_OIDC / ARM_USE_CLI / ARM_CLIENT_ID /
  # ARM_TENANT_ID from the environment the way the backend does. They default to
  # the Azure CLI so local runs work off `az login`; CI sets TF_VAR_use_oidc.
  #
  # `tofu init -backend=false` and `tofu validate` never contact the vault, so
  # the credential-free validate job in ci.yml keeps working.
  #
  # MIGRATION: the `fallback` lets the first run per environment read the state
  # while it is still unencrypted and write it back encrypted. Remove it once
  # dev, test and prod have each applied.
  # ---------------------------------------------------------------------------
  encryption {
    key_provider "azure_vault" "state" {
      vault_uri      = "https://kv-mytofustates.vault.azure.net"
      vault_key_name = var.app_name
      key_length     = 32

      use_oidc  = var.use_oidc
      use_cli   = !var.use_oidc
      client_id = var.arm_client_id
      tenant_id = var.arm_tenant_id
    }

    method "aes_gcm" "state" {
      keys = key_provider.azure_vault.state
    }

    method "unencrypted" "migrate" {}

    state {
      method = method.aes_gcm.state

      fallback {
        method = method.unencrypted.migrate
      }
    }

    plan {
      method = method.aes_gcm.state
    }
  }
}

provider "azurerm" {
  features {}
}

variable "app_name" {
  description = "Base name for all resources"
  default     = "k8s-ultimate-web-stack"
  type        = string
}

variable "env" {
  description = "Environment name"
  default     = "dev"
  type        = string
}

variable "use_oidc" {
  description = <<-EOT
    Authenticate the azure_vault state-encryption key provider with a GitHub
    OIDC token instead of the Azure CLI. Defaults to false so local runs use
    your `az login` session; CI sets TF_VAR_use_oidc=true.
  EOT
  type        = bool
  default     = false
}

variable "arm_client_id" {
  description = "Client ID for the key provider when use_oidc is true. Empty locally; CI sets TF_VAR_arm_client_id."
  type        = string
  default     = ""
}

variable "arm_tenant_id" {
  description = "Tenant ID for the key provider when use_oidc is true. Empty locally; CI sets TF_VAR_arm_tenant_id."
  type        = string
  default     = ""
}
