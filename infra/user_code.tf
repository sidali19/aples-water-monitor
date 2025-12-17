resource "kubernetes_deployment" "alpes_monitor_app" {
  metadata {
    name      = "alpes-monitor-app"
    namespace = kubernetes_namespace.alpes.metadata[0].name
    labels    = { app = "alpes-monitor-app" }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "alpes-monitor-app" } }
    template {
      metadata { labels = { app = "alpes-monitor-app" } }
      spec {
        container {
          name  = "alpes-monitor-app"
          image = var.user_code_image
          image_pull_policy = "IfNotPresent"
          command = ["dagster"]
          args    = ["api", "grpc", "-h", "0.0.0.0", "-p", "4000", "-m", "alpes_water_monitor.dagster_app.definitions"]
          env {
            name  = "DAGSTER_HOME"
            value = "/opt/dagster"
          }
          env {
            name = "CDSE_CLIENT_ID"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.cdse.metadata[0].name
                key  = "client_id"
              }
            }
          }
          env {
            name = "CDSE_CLIENT_SECRET"
            value_from {
              secret_key_ref {
                name = kubernetes_secret.cdse.metadata[0].name
                key  = "client_secret"
              }
            }
          }
          env {
            name  = "ALPES_MINIO_ENDPOINT"
            value = "http://minio:9000"
          }
          env {
            name  = "ALPES_MINIO_BUCKET"
            value = "alpes-water-monitor"
          }
          env {
            name  = "ALPES_MINIO_ACCESS_KEY"
            value = "minioadmin"
          }
          env {
            name  = "ALPES_MINIO_SECRET_KEY"
            value = "minioadmin"
          }
          port { container_port = 4000 }
          volume_mount {
            name       = "dagster-home"
            mount_path = "/opt/dagster"
          }
          volume_mount {
            name       = "dagster-storage"
            mount_path = "/opt/dagster/storage"
          }
          volume_mount {
            name       = "dagster-instance"
            mount_path = "/opt/dagster/dagster.yaml"
            sub_path   = "dagster.yaml"
          }
        }
        volume {
          name = "dagster-home"
          empty_dir {}
        }
        volume {
          name = "dagster-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.dagster_storage.metadata[0].name
          }
        }
        volume {
          name = "dagster-instance"
          config_map {
            name = kubernetes_config_map.dagster_instance.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "alpes_monitor_app" {
  metadata {
    name      = "alpes-monitor-app"
    namespace = kubernetes_namespace.alpes.metadata[0].name
  }
  spec {
    selector = { app = "alpes-monitor-app" }
    port {
      name        = "grpc"
      port        = 4000
      target_port = 4000
    }
  }
}
