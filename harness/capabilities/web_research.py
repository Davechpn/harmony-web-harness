from __future__ import annotations

import logfire
from pydantic_ai import RunContext
from pydantic_ai.capabilities import WebSearch
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.capabilities.hooks import ValidatedToolArgs
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import ToolDefinition

_PROVENANCE_INSTRUCTIONS = """\
Web Research Guidelines:
- Attach the source URL or reference to every factual claim derived from a web search.
- If a result is ambiguous or from an unverified source, say so explicitly.
- For pricing or availability, always include the date the data was retrieved.
- Do not assert facts that are not supported by a retrieved source; prefer to abstain.
"""


class WebResearchCapability(AbstractCapability):
    """Bundled web-research capability: WebSearch + source-citation instructions + provenance hook.

    Set defer_loading=True (the default) so instructions and tool schemas are
    withheld from the context until the agent explicitly activates this
    capability — keeping the default context small.
    """

    defer_loading: bool = True

    def __init__(self, *, defer_loading: bool = True) -> None:
        self.defer_loading = defer_loading
        self._web_search = WebSearch(defer_loading=defer_loading)

    def get_instructions(self):
        return _PROVENANCE_INSTRUCTIONS

    def get_toolset(self):
        return self._web_search.get_toolset()

    async def before_tool_execute(
        self,
        ctx: RunContext,
        *,
        call: ToolCallPart,
        tool_def: ToolDefinition,
        args: ValidatedToolArgs,
    ) -> ValidatedToolArgs:
        logfire.info(
            "tool called",
            tool=call.tool_name,
            tenant_id=getattr(ctx.deps, "tenant_id", None),
            thread_id=getattr(ctx.deps, "thread_id", None),
        )
        return args
