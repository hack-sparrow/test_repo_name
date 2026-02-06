"""Flask web application for Splitwise."""

from flask import Flask

from splitwise.app import SplitwiseApp


# Global app state (in-memory)
splitwise_app = SplitwiseApp()

# Admin credentials
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


def create_flask_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "splitwise-secret-key-change-in-production"

    from splitwise.web.routes import bp
    app.register_blueprint(bp)

    return app
