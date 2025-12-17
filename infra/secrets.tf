variable "cdse_client_id" {
  type        = string
  description = "CDSE client id"
}

variable "cdse_client_secret" {
  type        = string
  description = "CDSE client secret"
}

resource "kubernetes_secret" "cdse" {
  metadata {
    name      = "cdse-credentials"
    namespace = kubernetes_namespace.alpes.metadata[0].name
  }

  type = "Opaque"

  data = {
    client_id     = var.cdse_client_id
    client_secret = var.cdse_client_secret
  }
}
