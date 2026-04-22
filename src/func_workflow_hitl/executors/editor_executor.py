from agent_framework import (
    Agent,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)
from models.editor_approval_request import EditorApprovalRequest
from models.editor_approval_response import EditorApprovalResponse
from utils.response_format import extract_response_text


class EditorExecutor(Executor):
    def __init__(self, agent: Agent) -> None:
        super().__init__(id="editor_executor")
        self._agent = agent

    async def _edit_text(self, instruction: str) -> str:
        response = await self._agent.run(instruction)
        return extract_response_text(response)

    def _build_review_request(
        self,
        draft: str,
        proposed_text: str,
        feedback: str | None = None,
    ) -> EditorApprovalRequest:
        prompt = (
            "Review the edited draft below. Approve it if it is ready, or reject it with feedback.\n\n"
            f"Original draft:\n{draft}\n\n"
            f"Proposed edited version:\n{proposed_text}"
        )
        if feedback:
            prompt = f"{prompt}\n\nPrevious feedback applied:\n{feedback}"

        return EditorApprovalRequest(
            draft=draft,
            proposed_text=proposed_text,
            prompt=prompt,
        )

    @handler
    async def review(
        self,
        draft: str,
        ctx: WorkflowContext[str],
    ) -> None:
        proposed_text = await self._edit_text(
            "Review and improve the draft below. Return only the improved version.\n\n"
            f"Draft:\n{draft}"
        )
        await ctx.request_info(
            self._build_review_request(draft, proposed_text),
            EditorApprovalResponse,
        )

    @response_handler
    async def handle_review(
        self,
        original_request: EditorApprovalRequest,
        response: EditorApprovalResponse,
        ctx: WorkflowContext[str],
    ) -> None:
        if response.approved:
            await ctx.send_message(original_request.proposed_text)
            return

        revised_text = await self._edit_text(
            "Revise the edited draft using the human feedback below. Return only the revised version.\n\n"
            f"Original draft:\n{original_request.draft}\n\n"
            f"Current edited version:\n{original_request.proposed_text}\n\n"
            f"Human feedback:\n{response.feedback or 'Please improve the draft.'}"
        )
        await ctx.request_info(
            self._build_review_request(
                original_request.draft,
                revised_text,
                response.feedback,
            ),
            EditorApprovalResponse,
        )
