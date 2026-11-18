variable "region" {
  type    = string
  default = "us-east-1"
}

variable "owner" {
  type    = string
  default = "cost-lab"
}

variable "required_tags" {
  description = "Tags every resource must have (REQUIRED_TAGS supports up to 6)."
  type        = list(string)
  default     = ["CostCenter", "Owner", "Environment"]
  validation {
    condition     = length(var.required_tags) >= 1 && length(var.required_tags) <= 6
    error_message = "REQUIRED_TAGS accepts between 1 and 6 tag keys."
  }
}

variable "cost_center_budgets" {
  description = "Monthly budget in USD per CostCenter tag value."
  type        = map(number)
  default = {
    "web-team" = 100
    "data"     = 100
    "platform" = 50
  }
}

variable "budget_alert_email" {
  description = "Email for budget alerts (forecast over 80%, actual over 100%). Empty = no alerts."
  type        = string
  default     = ""
}

variable "create_config_recorder" {
  description = "Create an AWS Config recorder. Set false if the account already has one (only one is allowed per region)."
  type        = bool
  default     = true
}

variable "activate_cost_allocation_tags" {
  description = "Activate the required tags as cost-allocation tags. Needs the tags to exist in billing data first (about 24 hours after first use)."
  type        = bool
  default     = false
}
