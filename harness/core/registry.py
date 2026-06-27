from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml
from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from harness.core.models import TenantContext


class AgentSpec:
    """Resolved agent spec: the live Agent plus its harness metadata."""

    def __init__(
        self,
        agent: Agent[TenantContext, Any],
        slug: str,
        trigger_phrases: list[str],
        usage_limits: UsageLimits | None = None,
    ) -> None:
        self.agent = agent
        self.slug = slug
        self.trigger_phrases = trigger_phrases
        # Pass via agent.run(..., usage_limits=spec.usage_limits) at call sites.
        self.usage_limits = usage_limits


class AgentRegistry:
    """Loads and caches agents from YAML specs.

    Each spec file has a top-level `harness:` block with slug, output_type,
    usage_limits, and trigger_phrases. The rest of the YAML is passed through
    to Agent.from_file().
    """

    def __init__(self) -> None:
        self._specs: dict[str, AgentSpec] = {}

    def load(self, path: str | Path) -> AgentSpec:
        path = Path(path)
        raw = yaml.safe_load(path.read_text())
        harness_meta: dict[str, Any] = raw.pop("harness", {})

        slug = harness_meta.get("slug", path.stem)
        trigger_phrases = harness_meta.get("trigger_phrases", [])
        output_type_path: str | None = harness_meta.get("output_type")
        limits_cfg: dict[str, int] = harness_meta.get("usage_limits", {})

        output_type = _import_type(output_type_path) if output_type_path else str
        usage_limits = UsageLimits(**limits_cfg) if limits_cfg else None

        tmp_path = path.parent / f"_harness_tmp_{slug}.yaml"
        try:
            tmp_path.write_text(yaml.dump(raw))
            agent: Agent[TenantContext, Any] = Agent.from_file(
                str(tmp_path),
                deps_type=TenantContext,
                output_type=output_type,
            )
        finally:
            tmp_path.unlink(missing_ok=True)

        spec = AgentSpec(
            agent=agent,
            slug=slug,
            trigger_phrases=trigger_phrases,
            usage_limits=usage_limits,
        )
        self._specs[slug] = spec
        return spec

    def load_dir(self, dir_path: str | Path) -> None:
        for yaml_file in Path(dir_path).glob("*.yaml"):
            self.load(yaml_file)
        self.wire_delegations()

    def wire_delegations(self) -> None:
        """Register inter-agent delegation tools after all specs are loaded.

        Delegation follows the agent-as-tool pattern: the parent agent calls
        a tool that runs the sub-agent, sharing the same usage counter.
        Max two tiers — no standing hierarchy.
        """
        self._wire_event_planner_researcher()

    def _wire_event_planner_researcher(self) -> None:
        planner = self._specs.get("event_planner")
        researcher = self._specs.get("auction_researcher")
        if planner is None or researcher is None:
            return

        researcher_agent = researcher.agent
        researcher_limits = researcher.usage_limits

        @planner.agent.tool
        async def delegate_to_researcher(
            ctx: RunContext[TenantContext],
            task: str,
        ) -> str:
            """Delegate an auction research sub-task to the Auction Researcher agent."""
            result = await researcher_agent.run(
                task,
                deps=ctx.deps,
                usage=ctx.usage,
                usage_limits=researcher_limits,
            )
            output = result.output
            if hasattr(output, "findings"):
                return output.findings
            return str(output)

    def get(self, slug: str) -> AgentSpec | None:
        return self._specs.get(slug)

    def all_slugs(self) -> list[str]:
        return list(self._specs.keys())


def _import_type(dotted_path: str) -> type:
    module_path, _, attr = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, attr)
