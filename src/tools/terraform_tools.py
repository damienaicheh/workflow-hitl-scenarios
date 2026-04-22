import json
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated

from agent_framework import tool
from pydantic import Field


class TerraformTools:
    """Terraform validation and formatting via subprocess."""

    @tool(
        name="validate_terraform",
        description="Validate Terraform files by running terraform init + validate in a temp directory.",
        approval_mode="never_require",
    )
    async def validate_terraform(
        self,
        terraform_files_json: Annotated[
            str,
            Field(
                description=(
                    "JSON string: list of objects with 'filename' and 'content' keys "
                    "representing Terraform files to validate."
                )
            ),
        ],
    ) -> str:
        files = json.loads(terraform_files_json)
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                filepath = Path(tmpdir) / f["filename"]
                filepath.write_text(f["content"], encoding="utf-8")

            # terraform init (minimal, no backend)
            init_result = subprocess.run(
                ["terraform", "init", "-backend=false", "-no-color"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if init_result.returncode != 0:
                return json.dumps({
                    "valid": False,
                    "errors": [f"terraform init failed: {init_result.stderr.strip()}"],
                    "warnings": [],
                })

            # terraform validate
            validate_result = subprocess.run(
                ["terraform", "validate", "-json", "-no-color"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            try:
                output = json.loads(validate_result.stdout)
            except json.JSONDecodeError:
                return json.dumps({
                    "valid": False,
                    "errors": [validate_result.stderr.strip() or "Unknown validation error"],
                    "warnings": [],
                })

            errors = [
                d.get("detail", d.get("summary", "Unknown error"))
                for d in output.get("diagnostics", [])
                if d.get("severity") == "error"
            ]
            warnings = [
                d.get("detail", d.get("summary", "Unknown warning"))
                for d in output.get("diagnostics", [])
                if d.get("severity") == "warning"
            ]
            return json.dumps({
                "valid": output.get("valid", False),
                "errors": errors,
                "warnings": warnings,
            })

    @tool(
        name="format_terraform",
        description="Format Terraform files using terraform fmt and return the formatted content.",
        approval_mode="never_require",
    )
    async def format_terraform(
        self,
        terraform_files_json: Annotated[
            str,
            Field(
                description=(
                    "JSON string: list of objects with 'filename' and 'content' keys "
                    "representing Terraform files to format."
                )
            ),
        ],
    ) -> str:
        files = json.loads(terraform_files_json)
        with tempfile.TemporaryDirectory() as tmpdir:
            for f in files:
                filepath = Path(tmpdir) / f["filename"]
                filepath.write_text(f["content"], encoding="utf-8")

            subprocess.run(
                ["terraform", "fmt", "-no-color"],
                cwd=tmpdir,
                capture_output=True,
                text=True,
                timeout=30,
            )

            formatted = []
            for f in files:
                filepath = Path(tmpdir) / f["filename"]
                formatted.append({
                    "filename": f["filename"],
                    "content": filepath.read_text(encoding="utf-8"),
                })
            return json.dumps(formatted)
