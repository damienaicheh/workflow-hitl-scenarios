variable "domain" {
  description = "Azure deployment domain"
  type        = string
  default     = "wkf"
}

variable "workload" {
  description = "Azure deployment workload"
  type        = string
  default     = "hitl"
}

variable "environment" {
  description = "The environment deployed"
  type        = string
  default     = "dev"
  validation {
    condition     = can(regex("(dev|stg|pro)", var.environment))
    error_message = "The environment value must be a valid."
  }
}

variable "location" {
  description = "Azure deployment location"
  type        = string
  default     = "switzerlandnorth"
}

variable "region" {
  description = "Azure deployment region"
  type        = string
  default     = "sln"
}

variable "tags" {
  type        = map(any)
  description = "The custom tags for all resources"
  default     = {}
}

variable "resource_group_name" {
  type        = string
  description = "The name of the resource group"
  default     = ""
}

variable "acs_recipient_email" {
  type        = string
  description = "Recipient email"
}