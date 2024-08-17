# Request Event Function Details schema
# https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html#agents-lambda-input
from typing import Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


class Agent(BaseModel):
    name: str
    id: str
    alias: str
    version: str


class Parameters(BaseModel):
    name: str
    type: str
    value: str


class BedrockEvent(BaseModel):
    messageVersion: str
    agent: Agent
    inputText: str
    sessionId: str
    actionGroup: str
    function: str
    parameters: Optional[List[Parameters]]
    sessionAttributes: Dict[str, str]
    promptSessionAttributes: Dict[str, str]


# Response Event Function Details schema
# https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html#agents-lambda-response
class ResponseBody(BaseModel):
    body: str


class FunctionResponseBody(BaseModel):
    responseState: Optional[Literal["FAILURE", "REPROMPT"]] = Field(default=None)
    responseBody: Dict[str, ResponseBody]


class Response(BaseModel):
    actionGroup: str
    function: str
    functionResponse: FunctionResponseBody


class VectorSearchConfiguration(BaseModel):
    numberOfResults: int
    filter: dict


class RetrievalConfiguration(BaseModel):
    vectorSearchConfiguration: VectorSearchConfiguration


class KnowledgeBaseConfiguration(BaseModel):
    knowledgeBaseId: str
    retrievalConfiguration: RetrievalConfiguration


class BedrockResponseEvent(BaseModel):
    messageVersion: str
    response: Response
    sessionAttributes: Optional[Dict[str, str]] = None
    promptSessionAttributes: Optional[Dict[str, str]] = None
    knowledgeBasesConfiguration: Optional[List[KnowledgeBaseConfiguration]] = None

    @staticmethod
    def response_event_from_event(
        event: Union[BedrockEvent, dict], response_body: str, response_state: Literal["REPROMPT", "FAILURE"] = None
    ) -> "BedrockResponseEvent":
        if isinstance(event, dict):
            event = BedrockEvent.model_validate(event)
        resp = BedrockResponseEvent(
            messageVersion="1.0",
            response=Response(
                actionGroup=event.actionGroup,
                function=event.function,
                functionResponse=FunctionResponseBody(
                    # responseState=response_state,
                    responseBody={"TEXT": ResponseBody(body=response_body)}
                ),
            ),
            sessionAttributes=event.sessionAttributes,
            promptSessionAttributes=event.promptSessionAttributes,
        )
        if response_state:
            resp.response.functionResponse.responseState = response_state
        return resp

    def get_response_body(self) -> str:
        return self.response.functionResponse.responseBody["TEXT"].body
