# Azure-Inspect

A small tool to inspect an Azure subscription's **resources**, **cost**, and
**activity log** using a service principal (client-credentials auth). It ships
both a CLI and a Flask dashboard.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env   # then fill in your real service-principal credentials
```

Required environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `AZURE_TENANT_ID` | Entra ID tenant |
| `AZURE_CLIENT_ID` | Service-principal app id |
| `AZURE_CLIENT_SECRET` | Service-principal secret |
| `AZURE_SUBSCRIPTION_ID` | Target subscription |

> ⚠️ Never commit your real `.env`. It is git-ignored.

## CLI

```bash
azure-inspect resources                 # list resource groups
azure-inspect cost --days 30            # cost per resource group (trailing 30d)
azure-inspect activity --hours 24       # recent activity-log events
```

Or run as a module: `python -m azure_inspect ...`

## Dashboard

```bash
python -m azure_inspect.ui
# open http://127.0.0.1:5000
```

## Architecture

- `config` — loads credentials into a frozen `AzureConfig` dataclass
- `auth` — MSAL client-credentials token acquisition
- `models` — `ResourceGroup`, `CostSummary`, `ActivityEvent` dataclasses
- `resources` — ARM resource-group listing
- `costs` — Cost Management per-RG aggregation
- `logs` — Monitor activity-log fetch
- `cli` — argparse entry point
- `ui` — Flask dashboard

## Notes on permissions

The service principal needs at least **Reader** on the subscription and access
to the **Microsoft.CostManagement** data (Cost Management Reader role).
