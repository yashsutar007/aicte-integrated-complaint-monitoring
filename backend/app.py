# Destination: backend/app.py (replace existing)
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from routes.auth import auth_bp
from routes.assignments import assignments_bp, bureaus_bp
from routes.complaints import complaints_bp
from routes.coordination import coordination_bp
from routes.dashboard import dashboard_bp
from routes.institutions import institutions_bp
from routes.overlap import overlap_bp
from routes.workflow import workflow_bp

load_dotenv(Path(__file__).resolve().parent / ".env")


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        JWT_SECRET_KEY=os.getenv(
            "JWT_SECRET_KEY",
            "local-development-secret-change-before-deployment",
        ),
        JWT_ACCESS_TOKEN_EXPIRES=timedelta(minutes=30),
        MAX_CONTENT_LENGTH=10 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    allowed_origins = [
        item.strip()
        for item in os.getenv(
            "FRONTEND_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if item.strip()
    ]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})
    JWTManager(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(bureaus_bp)
    app.register_blueprint(assignments_bp)
    app.register_blueprint(institutions_bp)
    app.register_blueprint(complaints_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(overlap_bp)
    app.register_blueprint(coordination_bp)
    app.register_blueprint(workflow_bp)

    @app.get("/")
    def index():
        return jsonify({"success": True, "message": "AikyaTrace Complaint Monitoring API is running"})

    @app.get("/api/health")
    def health():
        return jsonify({"success": True, "status": "healthy", "service": "aikyatrace-api"})

    @app.errorhandler(413)
    def file_too_large(_error):
        return jsonify({"success": False, "message": "Request exceeds the 10 MB size limit."}), 413

    return app


app = create_app()

if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "0").lower() in ("1", "true", "yes")
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=debug_enabled)
