import os
import json
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities import parameters
from authlib.integrations.starlette_client import OAuth, OAuthError
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

load_dotenv()

logger = Logger(service="gradio_app.oauth.okta")


def get_user(request: Request) -> Optional[str]:
    return request.session.get("user")


def init_okta(app: FastAPI):
    # Configure OAuth
    if okta_secret_arn := os.getenv("OKTA_SECRET_ARN"):
        logger.info(f"Getting Okta secret from {okta_secret_arn}")
        okta_secret = json.loads(parameters.get_secret(okta_secret_arn))
    oauth = OAuth()
    okta_issuer = os.getenv("OKTA_OAUTH2_ISSUER") or okta_secret.get("OKTA_OAUTH2_ISSUER")
    oauth.register(
        name="okta",
        client_id=os.getenv("OKTA_OAUTH2_CLIENT_ID") or okta_secret.get("OKTA_OAUTH2_CLIENT_ID"),
        client_secret=os.getenv("OKTA_OAUTH2_CLIENT_SECRET") or okta_secret.get("OKTA_OAUTH2_CLIENT_SECRET"),
        access_token_url=f"{okta_issuer}/v1/token",
        authorize_url=f"{okta_issuer}/v1/authorize",
        # redirect_uri=f"{os.getenv('HOST_NAME') or 'http://localhost:8080'}/auth",
        jwks_uri=f"{okta_issuer}/v1/keys",
        client_kwargs={"scope": "openid email profile"},
    )
    SECRET_KEY = os.getenv("SESSION_SECRET") or okta_secret.get("SESSION_SECRET")
    app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

    @app.route("/logout")
    async def logout(request: Request):
        request.session.pop("user", None)
        return RedirectResponse(url="/")

    @app.route("/login")
    async def login(request: Request):
        # This is the URL that the Okta login page will redirect back to after authentication
        return await oauth.okta.authorize_redirect(request, request.url_for("auth"))

    @app.route("/auth")
    async def auth(request: Request):
        try:
            access_token = await oauth.okta.authorize_access_token(request)
        except OAuthError:
            return RedirectResponse(url="/")
        request.session["user"] = dict(access_token)["userinfo"]
        return RedirectResponse(url="/")
