"""Data models returned by the Azure-Inspect inspectors."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ResourceGroup:
    """An Azure resource group."""

    name: str
    location: str
    provisioning_state: str = "Unknown"
    tags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_api(cls, payload: dict) -> "ResourceGroup":
        props = payload.get("properties", {})
        return cls(
            name=payload.get("name", ""),
            location=payload.get("location", "unknown"),
            provisioning_state=props.get("provisioningState", "Unknown"),
            tags=payload.get("tags") or {},
        )


@dataclass
class CostSummary:
    """Aggregated cost for a single resource group over a billing period."""

    resource_group: str
    currency: str
    cost: float


@dataclass
class ActivityEvent:
    """A single entry from the Azure activity log."""

    event_timestamp: datetime
    operation: str
    resource_group: str
    caller: str
    status: str

    @classmethod
    def from_api(cls, payload: dict) -> "ActivityEvent":
        props = payload.get("properties", {})
        caller = props.get("caller", "unknown")
        try:
            ts = datetime.fromisoformat(payload["eventTimestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            ts = datetime.min
        return cls(
            event_timestamp=ts,
            operation=props.get("operationName", "unknown"),
            resource_group=props.get("resourceGroupName", ""),
            caller=caller,
            status=props.get("status", "unknown"),
        )
