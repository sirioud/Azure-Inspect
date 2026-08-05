"""Azure tenant posture: access (RBAC role assignments) and governance gaps.

These are read-only ARM queries that work with a Contributor service principal
and form the "compliance / posture" surface of the dashboard:

* ``list_role_assignments`` — who has what role at subscription / RG scope.
* ``governance_gaps`` — resource groups missing expected tagging (e.g. ``env``),
  a cheap proxy for policy-compliance posture without needing Policy Insights.
"""
from __future__ import annotations

from typing import Any

from ._http import azure_get
from .config import ARM_API_VERSION, AzureConfig
from .models import ComplianceState, RoleAssignment

_ARM_URL = "https://management.azure.com"

# Friendly names for the common built-in roles we expect to see.
_ROLE_NAMES = {
    "8e3af657-a8ff-443c-a75c-2fe8c4bcb635": "Owner",
    "acdd72a7-3385-48ef-bd42-f606fba81ae7": "Contributor",
    "b24988ac-6180-42a0-ab88-20f7382dd24c": "Reader",
    "18d7d88d-d35e-4fb5-a5c3-7773c20a72d9": "User Access Administrator",
    "72fafb9e-0641-4937-9268-a91bfd8191a3": "Cost Management Reader",
    "f25e0fa2-a7c8-4377-a259-31e6efdf1d16": "Log Analytics Reader",
}


def _role_name(role_def_id: str) -> str:
    rid = role_def_id.rstrip("/").split("/")[-1]
    return _ROLE_NAMES.get(rid, rid)


def list_role_assignments(cfg: AzureConfig) -> list[RoleAssignment]:
    """Return all RBAC role assignments visible at subscription scope.

    Includes assignments made directly on the subscription and any inherited
    from resource groups (Azure returns the flattened list for the scope).

    Raises:
        RuntimeError: on persistent non-2xx responses from the ARM API.
    """
    url = (
        f"{_ARM_URL}/subscriptions/{cfg.subscription_id}"
        f"/providers/Microsoft.Authorization/roleAssignments"
        f"?api-version=2022-04-01&$top=200"
    )
    items = azure_get(cfg, url, paginate=True)
    out: list[RoleAssignment] = []
    for it in items:
        props = it.get("properties", {})
        role_def = props.get("roleDefinitionId", "")
        principal = props.get("principalId", "")
        scope = props.get("scope", "")
        # Derive the resource group name from the scope if present.
        rg = ""
        if "/resourceGroups/" in scope:
            rg = scope.split("/resourceGroups/")[1].split("/")[0]
        out.append(
            RoleAssignment(
                role=_role_name(role_def),
                principal_id=principal,
                scope="subscription" if scope == f"/subscriptions/{cfg.subscription_id}" else rg or scope,
            )
        )
    return out


def governance_gaps(
    cfg: AzureConfig,
    required_tags: tuple[str, ...] = ("env",),
) -> list[ComplianceState]:
    """Flag resource groups missing one or more expected governance tags.

    A lightweight stand-in for policy compliance: every RG is expected to carry
    the ``required_tags`` (e.g. ``env``). Groups that don't are reported as gaps.

    Raises:
        RuntimeError: on persistent non-2xx responses from the ARM API.
    """
    from .resources import list_resource_groups

    gaps: list[ComplianceState] = []
    for rg in list_resource_groups(cfg):
        missing = [t for t in required_tags if t not in rg.tags]
        if missing:
            gaps.append(
                ComplianceState(
                    resource=rg.name,
                    resource_type="ResourceGroup",
                    issue=f"missing tag(s): {', '.join(missing)}",
                    compliant=False,
                )
            )
    return gaps


def posture_summary(cfg: AzureConfig) -> dict[str, Any]:
    """Combine access + governance signals into one dashboard payload."""
    roles = list_role_assignments(cfg)
    gaps = governance_gaps(cfg)
    # Count distinct principals by role for a compact headline.
    by_role: dict[str, int] = {}
    for r in roles:
        by_role[r.role] = by_role.get(r.role, 0) + 1
    return {
        "role_assignments": [
            {"role": r.role, "principal_id": r.principal_id, "scope": r.scope}
            for r in roles
        ],
        "roles_breakdown": by_role,
        "governance_gaps": [
            {"resource": g.resource, "resource_type": g.resource_type, "issue": g.issue}
            for g in gaps
        ],
        "governance_gap_count": len(gaps),
    }
