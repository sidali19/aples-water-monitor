resource "kubernetes_deployment" "minio" {
  metadata {
    name      = "minio"
    namespace = kubernetes_namespace.alpes.metadata[0].name
    labels    = { app = "minio" }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "minio" } }
    template {
      metadata { labels = { app = "minio" } }
      spec {
        container {
          name  = "minio"
          image = "minio/minio:RELEASE.2025-09-07T16-13-09Z-cpuv1"
          args  = ["server", "/data", "--console-address", ":9001"]
          env {
            name  = "MINIO_ROOT_USER"
            value = "minioadmin"
          }
          env {
            name  = "MINIO_ROOT_PASSWORD"
            value = "minioadmin"
          }
          port { container_port = 9000 }
          port { container_port = 9001 }
        volume_mount {
          name       = "data"
          mount_path = "/data"
        }
      }
      volume {
        name = "data"
        empty_dir {}
      }
    }
  }
}
}

resource "kubernetes_service" "minio" {
  metadata {
    name      = "minio"
    namespace = kubernetes_namespace.alpes.metadata[0].name
  }
  spec {
    selector = { app = "minio" }
    port {
      name        = "api"
      port        = 9000
      target_port = 9000
    }
    port {
      name        = "console"
      port        = 9001
      target_port = 9001
    }
  }
}
