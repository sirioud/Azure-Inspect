from flask import Flask, render_template, request
import os

from azure_inspect.config import load_config
from azure_inspect.resources import list_resource_groups
from azure_inspect.logs import get_activity_log
from azure_inspect.costs import cost_by_resource_group


def create_app():
    app = Flask(__name__)
    
    # Configure Flask app with essential settings
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    
    config = load_config()

    @app.route("/")
    def dashboard():

        resources = list_resource_groups(config.subscription_id, top=10)
        activity = get_activity_log(config.subscription_id, hours=6)
        costs = cost_by_resource_group(config.subscription_id)

        return render_template(
            "dashboard.html",
            resources=resources,
            activity=activity,
            costs=costs
        )

    @app.route("/resources")
    def resources():

        top = int(request.args.get("top", 50))

        data = list_resource_groups(
            config.subscription_id,
            top=top
        )

        return render_template(
            "resources.html",
            resources=data
        )

    @app.route("/activity")
    def activity():

        hours = int(request.args.get("hours", 24))

        data = get_activity_log(
            config.subscription_id,
            hours=hours
        )

        return render_template(
            "activity.html",
            activity=data
        )

    @app.route("/costs")
    def costs():

        data = cost_by_resource_group(
            config.subscription_id
        )

        return render_template(
            "costs.html",
            costs=data
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)