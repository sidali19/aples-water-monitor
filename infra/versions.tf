terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.25"
    }
  }
}

variable "kube_context" {
  type        = string
  description = "Kube context to use"
  default     = "k3d-alpes"
}

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = var.kube_context
}
