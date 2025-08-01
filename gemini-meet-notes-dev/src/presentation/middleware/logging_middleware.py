"""
Logging middleware for request/response tracking.
"""
import logging
import time
import json
from functools import wraps
from flask import request, g

logger = logging.getLogger(__name__)


def setup_logging():
    """Set up structured logging for Cloud Run."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'  # Cloud Run will add timestamp
    )
    
    # Set up structured logging
    class StructuredFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                'severity': record.levelname,
                'message': record.getMessage(),
                'timestamp': self.formatTime(record),
                'module': record.module
            }
            
            # Add trace context if available (for Cloud Logging)
            if hasattr(g, 'trace_id'):
                log_entry['logging.googleapis.com/trace'] = g.trace_id
            
            return json.dumps(log_entry)
    
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    
    root_logger = logging.getLogger()
    root_logger.handlers = []
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


def log_requests(f):
    """Decorator to log incoming requests and responses."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start_time = time.time()
        
        # Extract trace ID from Cloud Run headers
        trace_header = request.headers.get('X-Cloud-Trace-Context', '')
        if trace_header:
            trace_id = trace_header.split('/')[0]
            g.trace_id = f"projects/{request.headers.get('X-Google-Cloud-Project', 'unknown')}/traces/{trace_id}"
        
        # Log request
        logger.info(
            "Request started",
            extra={
                'method': request.method,
                'path': request.path,
                'user_agent': request.headers.get('User-Agent', ''),
                'content_length': request.content_length
            }
        )
        
        try:
            result = f(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log successful response
            logger.info(
                "Request completed",
                extra={
                    'method': request.method,
                    'path': request.path,
                    'duration_seconds': duration,
                    'status': 'success'
                }
            )
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error
            logger.error(
                "Request failed",
                extra={
                    'method': request.method,
                    'path': request.path,
                    'duration_seconds': duration,
                    'error': str(e),
                    'status': 'error'
                }
            )
            raise
    
    return decorated_function