import json
from typing import Union

from pydantic import BaseModel
from cdk.models import BedrockEvent, BedrockResponseEvent
import requests
from aws_lambda_powertools import Logger

logger = Logger(service="web_search", level="INFO", log_uncaught_exceptions=True)


def get_jina_key() -> str:
    # TODO: Move to secrets manager
    return "jina_97228772f32c4a16940e126332078a54xPAPfYHZwAkQ4tCUNn4USrROSqSe"


def get_jina_auth_header() -> dict:
    return {"Authorization": f"Bearer {get_jina_key()}"}


class JinaError(BaseModel):
    status_code: int
    message: str


def jina_search(query: str) -> Union[str, JinaError]:
    base_url = "https://s.jina.ai/"
    headers = get_jina_auth_header()
    headers["Accept"] = "application/json"
    query = requests.utils.quote(query)
    logger.info(f"Searching query: '{query}'")
    resp = requests.get(base_url + query, headers=headers)
    # TODO: handle response status code != 200
    if resp.status_code != 200:
        logger.error(f"Failed to search query: {query}. Status code: {resp.status_code}. Response: {resp.text}")
        return JinaError(status_code=resp.status_code, message=str(resp.text))
    data = json.loads(resp.text).get("data") or []
    urls = list(map(lambda x: x.get("url"), data))
    logger.info(f"Response urls: {urls} ...", urls=urls)
    for i, item in enumerate(data):
        # Limit content to 4000 characters
        data[i]["content"] = item.get("content")[:4000]
    return json.dumps(data)


def jina_retrieve(url: str) -> Union[str, JinaError]:
    base_url = "https://r.jina.ai/"
    headers = get_jina_auth_header()
    headers["Accept"] = "application/json"
    logger.info(f"Retrieving url: {url}")
    resp = requests.get(base_url + url, headers=headers)
    if resp.status_code != 200:
        logger.error(f"Failed to retrieve url: {url}. Status code: {resp.status_code}. Response: {resp.text}")
        return JinaError(status_code=resp.status_code, message=resp.text)
    data = json.loads(resp.text).get("data") or []
    # Limit content to 20000 characters
    data["content"] = data.get("content")[:20000]
    return json.dumps(data)


@logger.inject_lambda_context
def lambda_handler(event: dict, context) -> dict:

    bedrock_event = BedrockEvent.model_validate(event)

    if bedrock_event.function.lower() == "search":
        query = list(map(lambda x: x.value, filter(lambda x: x.name == "query", bedrock_event.parameters)))[0]
        response = jina_search(query)
        if isinstance(response, JinaError):
            # Try search again
            return BedrockResponseEvent.response_event_from_event(
                bedrock_event, response.message, response_state="REPROMPT"
            ).model_dump()

    elif bedrock_event.function.lower() == "retrieve":
        url = list(map(lambda x: x.value, filter(lambda x: x.name == "url", bedrock_event.parameters)))[0]
        response = jina_retrieve(url)
        if isinstance(response, JinaError):
            # Dont retry retrieve
            return BedrockResponseEvent.response_event_from_event(bedrock_event, response.message).model_dump()

    else:
        error_msg = f"Invalid function: {bedrock_event.function}"
        logger.error(error_msg)
        return BedrockResponseEvent.response_event_from_event(
            bedrock_event, error_msg, response_state="FAILURE"
        ).model_dump()

    return BedrockResponseEvent.response_event_from_event(bedrock_event, response).model_dump()


if __name__ == "__main__":
    import argparse
    from unittest.mock import MagicMock

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=["search", "retrieve"], help="Specify the action to perform: search, retrieve"
    )
    parser.add_argument("-q", "--query", help="Query string")
    parser.add_argument("-u", "--url", help="URL to retrieve")
    args = parser.parse_args()
    event = BedrockEvent(
        messageVersion="1.0",
        agent={"name": "web_search", "id": "web_search", "alias": "web_search", "version": "1.0"},
        inputText="input_text",
        sessionId="session_id",
        actionGroup="action_group",
        function=args.action,
        parameters=[
            {
                "name": "query" if args.query else "url",
                "type": "string",
                "value": args.query if args.query else args.url,
            }
        ],
        sessionAttributes={},
        promptSessionAttributes={},
    ).model_dump()

    resp_dict = lambda_handler(event, MagicMock())
    assert isinstance(resp_dict, dict)
    response = BedrockResponseEvent.model_validate(resp_dict)
    print("----")
    # print(type(response.get_response_body()))
    print(response.get_response_body())
