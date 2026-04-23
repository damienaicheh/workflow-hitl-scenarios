from pydantic import BaseModel, Field

class InfraRequest(BaseModel):
 
    """Structured input for an Azure infrastructure deployment request."""

    service: str = Field(description="Azure service to deploy (e.g. App Service, AKS, Storage Account)")
    region: str = Field(description="Azure region (e.g. westeurope, francecentral)")
    options: str | None = Field(default=None, description="Additional options: SKU, tier, features, etc.")

