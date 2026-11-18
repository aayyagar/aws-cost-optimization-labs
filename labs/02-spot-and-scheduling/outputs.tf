output "autoscaling_group" {
  value = aws_autoscaling_group.web.name
}

output "scheduler_function" {
  value = aws_lambda_function.scheduler.function_name
}

output "scheduled_instance" {
  value = aws_instance.dev.id
}

output "try_it" {
  value = <<-EOT
    See which instances are Spot:
      aws ec2 describe-instances --filters Name=tag:aws:autoscaling:groupName,Values=${aws_autoscaling_group.web.name} \
        --query 'Reservations[].Instances[].[InstanceId,InstanceType,InstanceLifecycle||`on-demand`]' --output table
    Stop the tagged instance now (what the 19:00 schedule does):
      aws lambda invoke --function-name ${aws_lambda_function.scheduler.function_name} --payload '{"action":"stop"}' --cli-binary-format raw-in-base64-out out.json && cat out.json
  EOT
}
