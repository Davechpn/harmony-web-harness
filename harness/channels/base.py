from __future__ import annotations

from typing import Any, Protocol

from harness.core.models import InboundMessage, OutboundMessage


class ChannelAdapter(Protocol):
    """Contract every channel adapter must satisfy.

    Adapters contain zero agent logic — only translate between the channel's
    native wire format and the canonical InboundMessage / OutboundMessage.
    """

    def parse(self, raw: dict[str, Any]) -> InboundMessage:
        """Translate a channel-native payload into a canonical InboundMessage."""
        ...

    async def deliver(self, msg: OutboundMessage) -> None:
        """Send a canonical OutboundMessage back to the channel."""
        ...
