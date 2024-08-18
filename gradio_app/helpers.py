from time import time
import os
import boto3
from starlette.requests import Request
from aws_lambda_powertools import Logger
from dotenv import load_dotenv

load_dotenv()

logger = Logger(service="gradio_app.helpers")


def request_as_dict(request: Request) -> dict:
    """Convert a Starlette request object to a flat dict"""
    # https://www.starlette.io/requests/
    return dict(
        url=request.url,
        method=request.method,
        headers=dict(request.headers),
        session_hash=request.session_hash,
        query_string=dict(request.query_params),
        username=request.username,
        host=request.client.host,
        cookies=request.cookies,
    )


class Boto:
    # A class to hold the client so that it can be reused
    _br_client: boto3.client = None
    _brrt_client: boto3.client = None
    _s3_client: boto3.client = None
    _session: boto3.Session = None

    @property
    def session(self) -> boto3.Session:
        if not self._session:
            logger.debug("Creating a new boto3 session")
            start_time = time()
            self._session = boto3.Session(region_name=os.environ.get("AWS_REGION"))
            logger.debug(f"Session created in {time() - start_time:.2f} seconds")
        return self._session

    def client(self, service: str) -> boto3.client:
        logger.debug(f"Creating a new boto3 client for service: {service}")
        start_time = time()
        client = self.session.client(service, region_name=os.environ.get("AWS_REGION"))
        logger.debug(f"Client created in {time() - start_time:.2f} seconds")
        return client

    @property
    def bedrock_runtime_client(self):
        if not self._brrt_client:
            self._brrt_client = self.client("bedrock-agent-runtime")
        logger.debug("reusing exiting bedrock runtime client")
        return self._brrt_client

    @property
    def bedrock_client(self):
        if not self._br_client:
            self._br_client = self.client("bedrock-agent")
        logger.debug("reusing exiting bedrock client")
        return self._br_client

    @property
    def s3_client(self):
        if not self._s3_client:
            self._s3_client = self.client("s3")
        logger.debug("reusing exiting s3 client")
        return self._s3_client


BOTO = Boto()
