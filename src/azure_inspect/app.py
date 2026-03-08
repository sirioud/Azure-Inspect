from flask import Flask, jsonify, request
import os

from .config import load_config
from .resources import list_resource_groups
from .logs import get_activity_log
from .costs import cost_by_resource_group

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

cfg = load_config()


@app.route("/resources")
def resources():
    data = list_resource_groups(cfg.subscription_id)
    return jsonify(data)


@app.route("/logs")
def logs():
    last_hours = int(request.args.get("last_hours", 24))

    data = get_activity_log(cfg.subscription_id, hours=last_hours)
    return jsonify(data)


@app.route("/costs")
def costs():
    data = cost_by_resource_group(cfg.subscription_id)
    return jsonify(data)
