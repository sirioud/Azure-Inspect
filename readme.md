# Azure Inspect

Collects Azure tenant resource inventory, monitoring logs, and cost info.

## Structure
- `src/azure_inspect/` - core package
- `azure_inspect/cli.py` - command line entrypoint
- `azure_inspect/api.py` - API layer (future Flask UI) #check if flask will be used in course

## Quick start
1. Copy `.env.example` to `.env` and fill values
2. Install deps: `pip install -r requirements.txt`
3. Run CLI: `python -m azure_inspect.cli`
