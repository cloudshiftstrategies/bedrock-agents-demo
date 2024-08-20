from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import MutableHeaders
from aws_lambda_powertools import Logger

logger = Logger(service="gradio_app.middeleware")


class LambdaRequestLogger(BaseHTTPMiddleware):
    """Middleware to log the incoming request"""

    async def dispatch(self, request, call_next):
        logger.debug(f"Request: {request.method} {request.url}", request=request.scope)
        response = await call_next(request)
        return response


class XForwardedHostMiddleware(BaseHTTPMiddleware):
    """Middleware to set the host header using the X-Forwarded-Host header"""

    async def dispatch(self, request, call_next):
        mutable_req_hdrs = MutableHeaders(request.headers)
        if x_forwarded_host := mutable_req_hdrs.get("X-Forwarded-Host"):
            logger.debug(
                f"Replacing 'Host' header currently: '{mutable_req_hdrs.get('Host')}' "
                f"with 'X-Forwarded-Host' header value: '{x_forwarded_host}'"
            )
            mutable_req_hdrs["Host"] = x_forwarded_host
        request._headers = mutable_req_hdrs
        request.scope.update(headers=request.headers.raw)
        response = await call_next(request)
        return response
