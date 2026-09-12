"""
Request ID middleware for distributed tracing.
Adds unique request ID to all logs and responses.
"""
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import logging

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a unique request ID to each request.
    
    - Generates UUID if not present in headers
    - Adds request ID to all log messages
    - Includes request ID in response headers
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Get request ID from header or generate new one
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Store in request state for access in endpoints
        request.state.request_id = request_id
        
        # Add to log context (if using structlog)
        try:
            import structlog
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
            )
        except ImportError:
            # Fallback for standard logging
            pass
        
        # Process request
        response = await call_next(request)
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id
        
        return response


class UserContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds user context to logs.
    
    - Extracts user ID from request state
    - Adds user ID to log context for tracing
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        # Get user ID from request state (set by auth middleware)
        user_id = getattr(request.state, 'user_id', None)
        user_role = getattr(request.state, 'user_role', None)
        
        # Add to log context
        if user_id:
            try:
                import structlog
                structlog.contextvars.bind_contextvars(
                    user_id=user_id,
                    user_role=user_role,
                )
            except ImportError:
                # Fallback for standard logging
                logger.extra = {'user_id': user_id, 'user_role': user_role}
        
        # Process request
        response = await call_next(request)
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all requests with timing information.
    Logs only slow requests (>1s) to reduce log volume.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        import time
        
        # Record start time
        start_time = time.time()
        
        # Get request info
        request_id = getattr(request.state, 'request_id', 'unknown')
        method = request.method
        path = request.url.path
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.time() - start_time) * 1000
        
        # Log only slow requests (>1 second) to reduce log volume
        if duration_ms > 1000:
            logger.warning(
                f"Slow request: {method} {path} - {response.status_code} ({duration_ms:.2f}ms)",
                extra={
                    'request_id': request_id,
                    'method': method,
                    'path': path,
                    'status_code': response.status_code,
                    'duration_ms': duration_ms,
                }
            )
        
        return response
