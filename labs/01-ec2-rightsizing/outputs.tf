output "instances" {
  description = "Instance IDs by name"
  value       = { for k, v in aws_instance.lab : k => v.id }
}

output "next_step" {
  value = "Wait at least 24 hours for metrics, then run: python -m costlab rightsize --region ${var.region} --days 1 --html rightsizing.html"
}
