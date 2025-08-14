from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from routes.user_routes import user_bp
from routes.task_routes import task_bp
from routes.email_notifications import email_notifications_bp

app = Flask(__name__)
app.config.from_object(Config)

# ✅ Enable CORS for all routes and allow credentials
CORS(app, origins=Config.FRONTEND_ORIGIN, supports_credentials=True)

jwt = JWTManager(app)

# Register blueprints
app.register_blueprint(user_bp, url_prefix='/api/users')
app.register_blueprint(task_bp, url_prefix='/api/tasks')
app.register_blueprint(email_notifications_bp, url_prefix='/api/notifications/emails')

if __name__ == '__main__':
    app.run(debug=True)
