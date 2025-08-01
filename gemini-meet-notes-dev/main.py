"""
Main Cloud Run application entry point.
"""
import asyncio
import json
import logging
from flask import Flask, request, jsonify
from config.container import container
from src.presentation.middleware.logging_middleware import setup_logging, log_requests

# Set up logging
setup_logging()
logger = logging.getLogger(__name__)

# Create Flask app
app = Flask(__name__)


@app.route("/", methods=["POST"])
@log_requests
def handle_pubsub():
    """
    Handle Pub/Sub messages from Google Drive change notifications.
    This is the main endpoint that Cloud Run will invoke.
    """
    try:
        # Get request data
        request_data = request.get_json()
        if not request_data:
            logger.error("No JSON data in request")
            return jsonify({"error": "No JSON data"}), 400
        
        logger.info(f"Received request data: {json.dumps(request_data, indent=2)}")
        
        # Get handler from DI container
        pubsub_handler = container.get_pubsub_handler()
        
        # Handle the message (convert sync to async)
        result = asyncio.run(
            pubsub_handler.handle_pubsub_message(request_data)
        )
        
        # Return result
        status_code = 200 if result.get("success", False) else 500
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Error in main handler: {e}")
        return jsonify({
            "success": False,
            "error": f"Handler error: {str(e)}"
        }), 500


@app.route("/setup", methods=["POST"])
@log_requests
def handle_setup():
    """
    Handle infrastructure setup requests.
    This endpoint is used to set up Google Drive push notifications.
    """
    try:
        request_data = request.get_json() or {}
        
        # Get configuration
        config = container.config
        project_id = request_data.get("project_id", config.google_cloud.project_id)
        topic_path = request_data.get("topic_path", config.google_cloud.topic_path)
        
        logger.info(f"Setting up infrastructure for project: {project_id}")
        
        # Get handler from DI container
        setup_handler = container.get_setup_handler()
        
        # Handle the setup (convert sync to async)
        result = asyncio.run(
            setup_handler.handle_setup_request(project_id, topic_path)
        )
        
        # Return result
        status_code = 200 if result.get("success", False) else 500
        return jsonify(result), status_code
        
    except Exception as e:
        logger.error(f"Error in setup handler: {e}")
        return jsonify({
            "success": False,
            "error": f"Setup error: {str(e)}"
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "service": "gemini-meet-notes-dev"
    }), 200


@app.route("/config", methods=["GET"])
@log_requests
def get_config():
    """Get current configuration (for debugging)."""
    try:
        config = container.config
        return jsonify({
            "target_user_email": config.target_user_email,
            "project_id": config.google_cloud.project_id,
            "topic_name": config.google_cloud.pubsub_topic_name,
            "subscription_name": config.google_cloud.pubsub_subscription_name,
            "storage_path": config.storage_path,
            "log_level": config.log_level
        }), 200
    except Exception as e:
        logger.error(f"Error getting config: {e}")
        return jsonify({
            "error": f"Config error: {str(e)}"
        }), 500


if __name__ == "__main__":
    # For local development
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)