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

variable "instances" {
  description = "Lab instances: name => instance type and the steady CPU load (percent) to generate. 0 = idle."
  type = map(object({
    instance_type = string
    cpu_load      = number
  }))
  default = {
    "rs-oversized-web" = { instance_type = "t3.large", cpu_load = 8 }
    "rs-idle-box"      = { instance_type = "t3.medium", cpu_load = 0 }
    "rs-right-sized"   = { instance_type = "t3.micro", cpu_load = 6 }
    "rs-credit-burner" = { instance_type = "t3.small", cpu_load = 35 }
  }
}
