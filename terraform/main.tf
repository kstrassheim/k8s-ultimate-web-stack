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
  default     = "ultimate-web-stack"
  type        = string
}

variable env {
  description = "Environment name"
  default     = "dev"
  type        = string
}