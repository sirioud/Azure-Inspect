#!/usr/bin/env bash
# Grant the Azure-Inspect service principal the RBAC roles it needs.
#
# Run from a machine where an Entra admin is signed in (Owner / User Access
# Administrator at the right scopes) via:
#
#   az login
#   bash grant_sp_roles.sh
#
# The script reads the service-principal ids from your local .env and assigns
# LEAST-PRIVILEGE roles:
#
#   * Cost Management Reader  — needed for /api/costs (Cost Management query)
#     at subscription scope.
#   * Reader                  — needed for /api/resources (works already),
#     AND at the TENANT (directory) scope for /api/logs. The activity log is
#     a tenant-level resource; a subscription-scope Reader is not enough for
#     eventLogs/read at tenant scope.
#
# After assigning, the CLI/API may take 1-5 minutes to honour the new roles.
set -euo pipefail

# Load .env (same file the dashboard uses).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$SCRIPT_DIR"
ENV_FILE="$REPO_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

# shellcheck disable=SC1090
source <(grep -E '^(AZURE_SUBSCRIPTION_ID|AZURE_CLIENT_ID)=' "$ENV_FILE" | sed 's/^/export /')

SUB_ID="${AZURE_SUBSCRIPTION_ID}"
SP_CLIENT_ID="${AZURE_CLIENT_ID}"

if [[ -z "${SUB_ID:-}" || -z "${SP_CLIENT_ID:-}" ]]; then
  echo "ERROR: AZURE_SUBSCRIPTION_ID and/or AZURE_CLIENT_ID missing from .env." >&2
  exit 1
fi

echo "Subscription: $SUB_ID"
echo "Service principal (app id): $SP_CLIENT_ID"
echo

echo "Assigning Cost Management Reader at subscription scope..."
az role assignment create \
  --assignee "$SP_CLIENT_ID" \
  --role "Cost Management Reader" \
  --scope "/subscriptions/$SUB_ID" \
  >/dev/null

echo "Assigning Reader at subscription scope (covers resource listing)..."
az role assignment create \
  --assignee "$SP_CLIENT_ID" \
  --role "Reader" \
  --scope "/subscriptions/$SUB_ID" \
  >/dev/null || echo "  (Reader already assigned — skipping)"

echo
echo "NOTE: the activity log lives at TENANT scope. A subscription-scope Reader"
echo "is not enough for Microsoft.Insights/eventLogs/read against the tenant-level"
echo "endpoint. If /api/logs still 403s, ALSO assign Reader at tenant (directory)"
echo "scope via the Azure portal (Microsoft Entra ID -> Roles -> + Add, assigning"
echo "the service principal as Reader at the directory scope)."
echo
echo "Done. Re-test the dashboard endpoints after a minute or two."
