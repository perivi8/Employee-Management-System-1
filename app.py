from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from routes.user_routes import user_bp
from routes.task_routes import task_bp
from routes.email_notifications import email_notifications_bp

app = Flask(__name__)
app.config.from_object(Config)

# CORS: apply globally and allow Authorization
CORS(
    app,
    origins=Config.CORS_ORIGINS,
    supports_credentials=Config.CORS_SUPPORTS_CREDENTIALS,
    allow_headers=Config.CORS_ALLOW_HEADERS,
    expose_headers=Config.CORS_EXPOSE_HEADERS,
    methods=Config.CORS_METHODS,
)

# Ensure preflight handled
@app.before_request
def handle_options():
    if request.method == "OPTIONS":
        return "", 200

jwt = JWTManager(app)

# Health endpoint for debugging “Failed to fetch”
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# Register blueprints
app.register_blueprint(user_bp, url_prefix="/api/users")
app.register_blueprint(task_bp, url_prefix="/api/tasks")
app.register_blueprint(email_notifications_bp, url_prefix="/api/notifications/emails")

if __name__ == "__main__":
    # In production behind a proxy, also consider app.run(host="0.0.0.0", port=8000)
    app.run(debug=True)
