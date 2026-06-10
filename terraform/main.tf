# This stack provisions the Azure AD app registration that the
# k8s-ultimate-web-stack backend (../backend/) authenticates against.
#
# The backend (FastAPI + msal + azure-identity, see
# ../backend/requirements.in) obtains tokens via MSAL against the
# `azuread_application.reg` resource below; the Oauth2 scope exposed
# here (`user_impersonation` under `api://<client_id>`) is what the
# backend's `/.auth`-style routes validate.
#
# Locking the backend Python dependency tree (../backend/requirements.txt,
# generated from ../backend/requirements.in with `uv pip compile
# --universal --generate-hashes --python-version 3.12`) means the exact
# `msal` and `azure-identity` versions that talk to this app reg are
# pinned — re-running `uv pip sync` reproduces a byte-identical closure
# on every CI run and on the deployed pod.

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
  backend "azurerm" {
    resource_group_name  = "terraform"
    storage_account_name = "mytofustates"
    container_name       = "k8s-ultimate-web-stack"
    key                  = "dev.tfstate"
    use_azuread_auth     = true
  }
}

provider "azurerm" {
  features {}
}

variable app_name {
  description = "Base name for all resources"
  default     = "k8s-ultimate-web-stack"
  type        = string
}

variable env {
  description = "Environment name"
  default     = "dev"
  type        = string
}