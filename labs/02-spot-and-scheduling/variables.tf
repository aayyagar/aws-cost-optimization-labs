variable "region" {
  type    = string
  default = "us-east-1"
}

variable "cost_center" {
  type    = string
  default = "platform"
}

variable "owner" {
  type    = string
  default = "cost-lab"
}

variable "instance_types" {
  description = "Interchangeable instance types for the Spot pool. More types = more Spot capacity pools = fewer interruptions."
  type        = list(string)
  default     = ["t3.micro", "t3a.micro", "t3.small", "t3a.small"]
}

variable "on_demand_base" {
  description = "Instances that always run On-Demand; everything above runs on Spot."
  type        = number
  default     = 1
}

variable "daytime_capacity" {
  type    = number
  default = 3
}

variable "max_size" {
  type    = number
  default = 4
}

variable "time_zone" {
  description = "IANA time zone for the schedules"
  type        = string
  default     = "America/New_York"
}

variable "start_hour" {
  type    = number
  default = 7
}

variable "stop_hour" {
  type    = number
  default = 19
}

variable "schedule_tag_key" {
  type    = string
  default = "Schedule"
}

variable "schedule_tag_value" {
  type    = string
  default = "office-hours"
}
