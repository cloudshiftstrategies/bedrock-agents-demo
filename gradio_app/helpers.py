import os
import boto3
from starlette.requests import Request


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
    agent_id = os.environ.get("BEDROCK_AGENT_ID")
    agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID")

    @property
    def session(self) -> boto3.Session:
        if not self._session:
            self._session = boto3.Session(region_name=os.environ.get("AWS_REGION"))
        return self._session

    def client(self, service: str) -> boto3.client:
        return self.session.client(service, region_name=os.environ.get("AWS_REGION"))

    @property
    def bedrock_runtime_client(self):
        if not self._brrt_client:
            self._brrt_client = self.client("bedrock-agent-runtime")
        return self._brrt_client

    @property
    def bedrock_client(self):
        if not self._br_client:
            self._br_client = self.client("bedrock-agent")
        return self._br_client

    @property
    def s3_client(self):
        if not self._s3_client:
            self._s3_client = self.client("s3")
        return self._s3_client
