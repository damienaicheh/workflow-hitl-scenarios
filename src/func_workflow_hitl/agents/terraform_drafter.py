import os

from agent_framework import Agent
from azure.ai.projects.models import PromptAgentDefinition

from agent_framework.foundry import FoundryChatClient
from tools.azure_devops_tools import AzureDevOpsTools
from tools.terraform_tools import TerraformTools
from azure.ai.projects import AIProjectClient

def create_terraform_drafter_agent(project_client: AIProjectClient, foundry_client: FoundryChatClient) -> Agent:
    
    instructions = """"
        You are an IaC Deployment Assistant for Azure DevOps.
        You can generate, validate, format, and push Terraform code.
        Use Azure DevOps MCP tools when they help answer the user.
        Use push_terraform_branch to push files to a new branch.
        Use create_pull_request to create PRs after pushing code.
        Use validate_terraform and format_terraform before pushing.
    """
  
    terraform_drafter = project_client.agents.create_version(
        agent_name="TerraformDrafterAgent",
        definition=PromptAgentDefinition(
            model=os.environ["FOUNDRY_DEFAULT_MODEL"],
            instructions=instructions.strip(),
        ),
    )
     
    azure_devops_tools = AzureDevOpsTools(
        organization=os.environ["ADO_ORG"],
        auth_token=os.environ["ADO_PAT"],
        default_project=os.environ.get("ADO_DEFAULT_PROJECT"),
    )
     
    terraform_tools = TerraformTools() 
     
    return Agent(
        client=foundry_client,
        name=terraform_drafter.name,
        tools=[
            azure_devops_tools.build_ado_mcp_tool,
            azure_devops_tools.create_file_in_repo,
            terraform_tools.validate_terraform,
            terraform_tools.format_terraform,
        ],
    )
    
    