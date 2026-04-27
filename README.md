# Terraform Azure deployment

This repository contains Terraform code to deploy resources in Azure. Follow the steps below to set up and deploy your infrastructure.

Pick the Foundry public or private module you want to deploy.

```bash
cd infra
```

Login to Azure using the device code method:

```
az login --use-device-code
```

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
```

Terraform initialization, planning, and applying commands:
```bash
terraform init
```


```bash
terraform plan -out plan.out
```


```bash
terraform apply plan.out
```

Deploy the Function App using the Azure CLI:

```bash
func azure functionapp publish <function_app_name>
```

Update the ADO PAT (Azure DevOps Personal Access Token) in your Key Vault so that the Function App can access it securely.