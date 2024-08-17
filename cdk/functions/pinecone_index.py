#!/usr/bin/env python
import os
import json
from pinecone import Pinecone, ServerlessSpec
from aws_lambda_powertools import Logger
from aws_lambda_powertools.utilities import parameters
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_typing import events

logger = Logger(service="pinecone-index")
logger.setLevel("INFO")

DEFAULT_REGION = "us-east-1"
DEFAULT_CLOUD = "aws"
DEFAULT_METRIC = "cosine"
DEFAULT_DIMENSION = 1024
PINECONE_API_KEY_SECRET_ENV_NAME = "PINECONE_API_KEY_SECRET_NAME"


@logger.inject_lambda_context(log_event=True)
def lambda_handler(event: events.CloudFormationCustomResourceEvent, context: LambdaContext):
    secret_name = os.getenv(PINECONE_API_KEY_SECRET_ENV_NAME)
    logger.info(f"secret_name: {secret_name}")
    api_key: str = os.getenv("PINECONE_API_KEY") or json.loads(parameters.get_secret(secret_name)).get("apiKey")
    logger.info(f"api_key: {api_key[:5]}...")

    # Create a pinecone client
    pc = Pinecone(api_key=api_key)
    name = event["ResourceProperties"]["name"]

    props = dict(
        name=name,
        dimension=int(event["ResourceProperties"].get("dimension", DEFAULT_DIMENSION)),
        metric=event["ResourceProperties"].get("metric", DEFAULT_METRIC),
        spec=ServerlessSpec(
            cloud=event["ResourceProperties"].get("cloud", DEFAULT_CLOUD),
            region=event["ResourceProperties"].get("region", DEFAULT_REGION),
        ),
    )

    def describe_index(name: str) -> dict:
        logger.info(f"Describing index '{name}'")
        description = pc.describe_index(name).to_dict()
        logger.info(f"Index '{name}' description", description=description)
        return description

    def delete_index(name: str) -> dict:
        logger.info(f"Deleting index '{name}'")
        index_exists = any(filter(lambda i: i.name == name, pc.list_indexes().indexes))
        if index_exists:
            result = pc.delete_index(name)
            logger.info(f"Index '{name}' was deleted", result=result)
        else:
            logger.info(f"Index '{name}' does not exist, doing nothing")
        return {"name": name, "host": "none"}

    def create_index(name: str, dimension: int, metric: str, spec: ServerlessSpec) -> dict:
        logger.info(f"Creating index '{name}'", props=props)
        result = pc.create_index(name=name, dimension=dimension, metric=metric, spec=spec)
        logger.info(f"Index '{name}' was created", result=result)
        return describe_index(name)

    def replace_index(name: str, dimension: int, metric: str, spec: ServerlessSpec) -> dict:
        logger.info(f"Replacing index '{name}'")
        delete_index(name)
        return create_index(name, dimension, metric, spec)

    if event.get("RequestType") == "Delete":
        index = delete_index(name)
        return {}
    elif event.get("RequestType") == "Create":
        index = create_index(**props)
    elif event.get("RequestType") == "Update":
        index = replace_index(**props)
    return {"PhysicalResourceId": index["host"] + "/" + index["name"], "Data": index}


if __name__ == "__main__":
    import argparse
    from unittest.mock import MagicMock
    from dotenv import load_dotenv

    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Manage Pinecone indexes. PINECONE_API_KEY must be set in the environment or in AWS Secrets Manager"
    )
    parser.add_argument(
        "action", choices=["create", "delete", "update"], help="Specify the action to perform: create, delete"
    )
    parser.add_argument("-n", "--name", help="Name of the index")
    parser.add_argument(
        "-d",
        "--dimension",
        type=int,
        default=DEFAULT_DIMENSION,
        help=f"number of dimensions for the index. default: {DEFAULT_DIMENSION}",
    )
    parser.add_argument(
        "-m", "--metric", default=DEFAULT_METRIC, help=f"metric for the index. default: {DEFAULT_METRIC}"
    )
    parser.add_argument(
        "-r", "--region", default=DEFAULT_REGION, help=f"region for the index. default: {DEFAULT_REGION}"
    )
    parser.add_argument("-c", "--cloud", default=DEFAULT_CLOUD, help=f"cloud for the index. default: {DEFAULT_CLOUD}")

    args = parser.parse_args()
    event = {
        "RequestType": args.action.capitalize(),
        "ResourceProperties": dict(
            name=args.name, dimension=args.dimension, metric=args.metric, cloud=args.cloud, region=args.region
        ),
    }

    result = lambda_handler(event, MagicMock())
    print(json.dumps(result, indent=2))
