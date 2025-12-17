resource "kubernetes_namespace" "alpes" {
  metadata {
    name = "alpes-water-monitor"
  }
}
