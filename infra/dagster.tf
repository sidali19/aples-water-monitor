locals {
  ns                = kubernetes_namespace.alpes.metadata[0].name
  control_plane_img = var.control_plane_image
  user_code_img     = var.user_code_image
}

variable "control_plane_image" {
  type        = string
  description = "Dagster control-plane image"
  default     = "dagster/dagster-k8s:1.12.6"
}

variable "user_code_image" {
  type        = string
  description = "User code image (pipelines)"
  default     = "alpes-water-monitor:latest"
}

variable "storage_class_name" {
  type        = string
  description = "StorageClass for Dagster PVC"
  default     = "local-path"
}

# ConfigMaps: workspace and instance
resource "kubernetes_config_map" "dagster_workspace" {
  metadata {
    name      = "dagster-workspace"
    namespace = local.ns
  }
  data = {
    "workspace.yaml" = <<-EOF
      load_from:
        - grpc_server:
            host: alpes-monitor-app
            port: 4000
            location_name: alpes-monitor-app
    EOF
  }
}

resource "kubernetes_config_map" "dagster_instance" {
  metadata {
    name      = "dagster-instance"
    namespace = local.ns
  }
  data = {
    "dagster.yaml" = file("${path.module}/dagster_instance.yaml")
  }
}

# Shared storage for sqlite run/event/schedule DB and artifacts
resource "kubernetes_persistent_volume_claim" "dagster_storage" {
  metadata {
    name      = "dagster-storage"
    namespace = local.ns
  }
  wait_until_bound = false
  spec {
    access_modes = ["ReadWriteOnce"]
    storage_class_name = var.storage_class_name
    resources {
      requests = {
        storage = "1Gi"
      }
    }
  }
}

# Dagster webserver Deployment + Service
resource "kubernetes_deployment" "dagster_webserver" {
  metadata {
    name      = "dagster-webserver"
    namespace = local.ns
    labels    = { app = "dagster-webserver" }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "dagster-webserver" } }
    template {
      metadata { labels = { app = "dagster-webserver" } }
      spec {
        container {
          name  = "webserver"
          image = local.control_plane_img
          command = ["dagster-webserver"]
          args    = ["-w", "/opt/dagster/workspace.yaml", "-h", "0.0.0.0", "-p", "3000"]
          env {
            name  = "DAGSTER_HOME"
            value = "/opt/dagster"
          }
          env {
            name  = "DAGSTER_K8S_JOB_IMAGE"
            value = local.user_code_img
          }
          env {
            name  = "DAGSTER_K8S_JOB_NAMESPACE"
            value = local.ns
          }
          env {
            name  = "DAGSTER_K8S_JOB_IMAGE_PULL_POLICY"
            value = "IfNotPresent"
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
          port { container_port = 3000 }
          volume_mount {
            name       = "dagster-home"
            mount_path = "/opt/dagster"
          }
          volume_mount {
            name       = "dagster-storage"
            mount_path = "/opt/dagster/storage"
          }
          volume_mount {
            name       = "dagster-workspace"
            mount_path = "/opt/dagster/workspace.yaml"
            sub_path   = "workspace.yaml"
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
          name = "dagster-workspace"
          config_map {
            name = kubernetes_config_map.dagster_workspace.metadata[0].name
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

resource "kubernetes_service" "dagster_web" {
  metadata {
    name      = "dagster-webserver"
    namespace = local.ns
  }
  spec {
    selector = { app = "dagster-webserver" }
    port {
      name        = "http"
      port        = 3000
      target_port = 3000
    }
  }
}

# Dagster daemon Deployment
resource "kubernetes_deployment" "dagster_daemon" {
  metadata {
    name      = "dagster-daemon"
    namespace = local.ns
    labels    = { app = "dagster-daemon" }
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "dagster-daemon" } }
    template {
      metadata { labels = { app = "dagster-daemon" } }
      spec {
        container {
          name  = "daemon"
          image = local.control_plane_img
          command = ["dagster-daemon"]
          args    = ["run", "-w", "/opt/dagster/workspace.yaml"]
          env {
            name  = "DAGSTER_HOME"
            value = "/opt/dagster"
          }
          env {
            name  = "DAGSTER_K8S_JOB_IMAGE"
            value = local.user_code_img
          }
          env {
            name  = "DAGSTER_K8S_JOB_NAMESPACE"
            value = local.ns
          }
          env {
            name  = "DAGSTER_K8S_JOB_IMAGE_PULL_POLICY"
            value = "IfNotPresent"
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
          volume_mount {
            name       = "dagster-home"
            mount_path = "/opt/dagster"
          }
          volume_mount {
            name       = "dagster-storage"
            mount_path = "/opt/dagster/storage"
          }
          volume_mount {
            name       = "dagster-workspace"
            mount_path = "/opt/dagster/workspace.yaml"
            sub_path   = "workspace.yaml"
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
          name = "dagster-workspace"
          config_map { name = kubernetes_config_map.dagster_workspace.metadata[0].name }
        }
        volume {
          name = "dagster-instance"
          config_map { name = kubernetes_config_map.dagster_instance.metadata[0].name }
        }
      }
    }
  }
}
