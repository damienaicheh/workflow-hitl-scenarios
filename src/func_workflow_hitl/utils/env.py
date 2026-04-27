import os

from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential, DefaultAzureCredential


def get_first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return None


def require_env(*names: str) -> str:
    value = get_first_env(*names)
    if value:
        return value
    joined_names = ", ".join(names)
    raise ValueError(
        f"Missing required environment variable. Set one of: {joined_names}"
    )


def create_azure_credential():
    managed_identity_client_id = get_first_env(
        "AZURE_CLIENT_ID",
    )

    if not managed_identity_client_id:
        return AzureCliCredential()

    return DefaultAzureCredential(
        managed_identity_client_id=managed_identity_client_id,
        exclude_interactive_browser_credential=True,
    )


def create_foundry_client() -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["FOUNDRY_DEFAULT_MODEL"],
        credential=create_azure_credential(),
    )
