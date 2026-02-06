#!/usr/bin/env python3
"""Run the Splitwise web application."""

from splitwise.web import create_flask_app

app = create_flask_app()

if __name__ == "__main__":
    print("Starting Splitwise app at http://localhost:5000")
    print("Login with admin / admin123")
    app.run(debug=True, host="0.0.0.0", port=5000)
