"""Entry point so the dashboard can be launched with ``python -m azure_inspect.ui``.

Runs the Flask dashboard bound to localhost only, with the debugger off (the
Werkzeug debugger is a remote-code-execution risk if the bind address ever
leaves localhost). The systemd unit / supervisor should manage the process;
this is the manual-developer convenience path.
"""

from __future__ import annotations

from .app import create_app

if __name__ == "__main__":
    create_app().run(debug=False, host="127.0.0.1", port=5000)
