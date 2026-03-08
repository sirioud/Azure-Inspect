from dataclasses import dataclass
from typing import Optional


@dataclass
class ResourceGroup:
    name: str
    location: str
    provisioning_state: str
    tags: Optional[dict] = None


@dataclass
class CostSummary:
    resource_group: str
    cost: float


@dataclass
class ActivityEvent:
    operation: str
    status: str
    resource_group: Optional[str]
    caller: Optional[str]
