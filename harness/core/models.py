from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Channel(StrEnum):
    APP = "app"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    GMAIL = "gmail"
    SLACK = "slack"


class SenderType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"


class Attachment(BaseModel):
    media_type: str
    url: str
    filename: str | None = None


class InboundMessage(BaseModel):
    tenant_id: str
    channel: Channel
    thread_id: str
    message_id: str
    sender_type: SenderType
    sender_id: str
    text: str
    attachments: list[Attachment] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    reply_to: str | None = None
    locale: str = "en"
    timestamp: float  # unix epoch seconds


class TextBlock(BaseModel):
    type: str = "text"
    content: str


class DashboardBlock(BaseModel):
    type: str = "dashboard"
    title: str
    view_id: str
    params: dict[str, Any] = Field(default_factory=dict)
    scope: str = "thread"


class ApprovalCard(BaseModel):
    type: str = "approval"
    run_id: str
    action_label: str
    proposed_action: dict[str, Any]
    provenance: list[str] = Field(default_factory=list)
    approver_role_required: str = "group_admin"


MessageBlock = TextBlock | DashboardBlock | ApprovalCard


class OutboundMessage(BaseModel):
    tenant_id: str
    channel: Channel
    thread_id: str
    blocks: list[MessageBlock]
    reply_to: str | None = None
    sender_agent_id: str


class DeliveryWindow(BaseModel):
    tz: str = "UTC"
    start_hour: int = 7
    end_hour: int = 22
    urgent_exempt: bool = True


class TenantPolicy(BaseModel):
    tenant_id: str
    allowed_models: list[str] = Field(default_factory=list)
    require_hitl_for: list[str] = Field(default_factory=list)
    budget_limit_usd: float | None = None
    budget_used_usd: float = 0.0
    live_trading: bool = False
    delivery_window: DeliveryWindow = Field(default_factory=DeliveryWindow)
    guardrails: dict[str, Any] = Field(default_factory=dict)
    data_region: str = "default"
    retention_days: int = 90
    # thread_id → list of agent slugs that are members of that thread
    thread_agents: dict[str, list[str]] = Field(default_factory=dict)


class TenantContext(BaseModel):
    tenant_id: str
    locale: str
    thread_id: str
    message_id: str
    sender_id: str
    credentials: dict[str, str] = Field(default_factory=dict)
    policy: TenantPolicy


class SummaryOutput(BaseModel):
    summary: str
    key_points: list[str] = Field(default_factory=list)
    message_count: int = 0


class HandoverRequest(BaseModel):
    """Emitted by an agent tool when it wants to transfer the floor."""
    to: str
    reason: str
    context_summary: str
    artifacts: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    return_to: str | None = None


class HandoverEvent(BaseModel):
    """Visible thread event posted when the floor transfers between agents."""
    type: str = "handover"
    from_agent: str
    to_agent: str
    reason: str
    context_summary: str
    return_to: str | None = None


class EventPlannerOutput(BaseModel):
    plan: str
    next_steps: list[str] = Field(default_factory=list)
    handover: HandoverRequest | None = None


class AuctionResearchOutput(BaseModel):
    findings: str
    listings: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
