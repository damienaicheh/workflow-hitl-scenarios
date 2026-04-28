import json

from pydantic import BaseModel, Field


class TerraformFile(BaseModel):
    filename: str = Field(description="Terraform file name, for example 'main.tf'.")
    content: str = Field(description="Terraform file contents.")


class TerraformBundle(BaseModel):
    files: list[TerraformFile] = Field(
        min_length=1,
        description="Terraform files that make up the generated configuration.",
    )

    def to_json_list(self) -> str:
        return json.dumps(
            [terraform_file.model_dump(mode="json") for terraform_file in self.files],
            ensure_ascii=True,
        )
