from fastapi import Request
from aws_lambda_powertools import Logger

logger = Logger(service="gradio_app.fixes")


# Gradio mounted with fastapi via https in behind proxy returns wrong path
# https://github.com/gradio-app/gradio/issues/8073
def get_root_url(request: Request, route_path: str, root_path: str | None):
    """
    https://github.com/gradio-app/gradio/issues/8073#issuecomment-2139100287
    monkeypatch the root_path function and provide an absolute root_path without host instead.
    Since we aret not including the host it works behind a proxy.
    """
    logger.debug(
        f"get_root_url() monkey patch returning root_path: {root_path}",
        request_url_path=request.url.path,
        route_path=route_path,
        root_path=root_path,
    )
    return root_path
