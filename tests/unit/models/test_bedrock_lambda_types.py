from cdk.models.models import (
    BedrockEvent,
    BedrockResponseEvent,
    FunctionResponseBody,
    Response,
    ResponseBody,
)
from tests.unit.mock_data import bedrock_event


def test_bedrock_lambda_types_event():
    fn_event = BedrockEvent.model_validate(bedrock_event)
    assert isinstance(fn_event, BedrockEvent)


def test_bedrock_lambda_types_response():
    fn_resp = FunctionResponseBody(responseState="REPROMPT", responseBody={"TEXT": ResponseBody(body="response_text")})
    resp = BedrockResponseEvent(
        messageVersion="1.0",
        response=Response(actionGroup="action_group", function="function_name", functionResponse=fn_resp),
    )
    assert isinstance(resp, BedrockResponseEvent)


def test_bedrock_lambda_types_response_event_from_event():
    fr_event = BedrockResponseEvent.response_event_from_event(bedrock_event, "response_text")
    assert isinstance(fr_event, BedrockResponseEvent)
    assert fr_event.messageVersion == bedrock_event["messageVersion"]
    assert fr_event.sessionAttributes == bedrock_event["sessionAttributes"]
    assert fr_event.promptSessionAttributes == bedrock_event["promptSessionAttributes"]
    assert fr_event.response.actionGroup == bedrock_event["actionGroup"]
    assert fr_event.response.function == bedrock_event["function"]
    assert fr_event.response.functionResponse.responseState is None
    assert fr_event.response.functionResponse.responseBody["TEXT"].body == "response_text"


def test_bedrock_lambda_types_response_event_from_event_failure():
    fr_event = BedrockResponseEvent.response_event_from_event(bedrock_event, "response_text", response_state="FAILURE")
    assert fr_event.response.functionResponse.responseState == "FAILURE"
