from fastapi import FastAPI, Request
from starlette.responses import RedirectResponse
from aws_lambda_powertools import Logger

logger = Logger(service="gradio_app.fixes")


def issue_7943(app: FastAPI) -> None:
    @app.route("/theme.css", methods=["GET"])
    def theme_css(request: Request):
        # Bug in gradio mounted to a subpath behind a proxy
        # https://github.com/gradio-app/gradio/issues/7934
        logger.warning(f"Issue#7934 - Redirecting to /gradio/{request.url.path}")
        return RedirectResponse(url=f"/gradio{request.url.path}?{request.query_params}")

    @app.route("/queue/join", methods=["POST"])
    def queue_join(request: Request):
        # Bug in gradio mounted to a subpath behind a proxy
        # https://github.com/gradio-app/gradio/issues/7934
        logger.warning(f"Issue#7934 - Redirecting to /gradio/{request.url.path}")
        return RedirectResponse(url=f"/gradio{request.url.path}?{request.query_params}")

    @app.route("/queue/data", methods=["POST", "GET"])
    def queue_data(request: Request):
        # Bug in gradio mounted to a subpath behind a proxy
        # https://github.com/gradio-app/gradio/issues/7934
        logger.warning(f"Issue#7934 - Redirecting to /gradio/{request.url.path}")
        return RedirectResponse(url=f"/gradio{request.url.path}?{request.query_params}")
