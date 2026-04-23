# Azure Functions Python container with Terraform CLI
FROM mcr.microsoft.com/azure-functions/python:4-python3.11

# Install Terraform
RUN apt-get update && \
    apt-get install -y --no-install-recommends gnupg software-properties-common curl unzip && \
    curl -fsSL https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip -o /tmp/terraform.zip && \
    unzip /tmp/terraform.zip -d /usr/local/bin/ && \
    rm /tmp/terraform.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy shared tools from parent src/ directory
COPY tools/ /home/site/wwwroot/tools/

# Copy function app code
COPY func_workflow_hitl/host.json /home/site/wwwroot/
COPY func_workflow_hitl/requirements.txt /home/site/wwwroot/
COPY func_workflow_hitl/function_app.py /home/site/wwwroot/
COPY func_workflow_hitl/executors/ /home/site/wwwroot/executors/
COPY func_workflow_hitl/models/ /home/site/wwwroot/models/
COPY func_workflow_hitl/utils/ /home/site/wwwroot/utils/

# Install Python dependencies
RUN pip install --no-cache-dir -r /home/site/wwwroot/requirements.txt

ENV AzureWebJobsScriptRoot=/home/site/wwwroot \
    AzureFunctionsJobHost__Logging__Console__IsEnabled=true
