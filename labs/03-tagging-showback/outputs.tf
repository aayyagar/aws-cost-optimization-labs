output "config_rule" {
  value = aws_config_config_rule.required_tags.name
}

output "budgets" {
  value = [for b in aws_budgets_budget.cost_center : b.name]
}

output "check_compliance" {
  value = "aws configservice get-compliance-details-by-config-rule --config-rule-name ${aws_config_config_rule.required_tags.name} --compliance-types NON_COMPLIANT --query 'EvaluationResults[].EvaluationResultIdentifier.EvaluationResultQualifier.ResourceId'"
}
