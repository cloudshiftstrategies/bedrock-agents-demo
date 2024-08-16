from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any


# Define the data models for the Bedrock InvokeAgent response which is a very complex nested structure.
# Creating a pydatnic model for the response will make it easier to parse the response and extract the relevant information.
# https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/bedrock-agent-runtime/client/invoke_agent.html

class InferenceConfiguration(BaseModel):
    temperature: Optional[float]
    topP: Optional[float]
    topK: Optional[int]
    maximumLength: Optional[int]
    stopSequences: Optional[List[str]]


class TextSpan(BaseModel):
    start: int
    end: int


class TextResponsePart(BaseModel):
    text: str
    span: TextSpan


class GeneratedResponsePart(BaseModel):
    textResponsePart: TextResponsePart


class RetrievedReferenceContent(BaseModel):
    text: str


class RetrievedReferenceLocationS3(BaseModel):
    uri: str


class RetrievedReferenceLocation(BaseModel):
    type: str
    s3Location: RetrievedReferenceLocationS3


class RetrievedReference(BaseModel):
    content: RetrievedReferenceContent
    location: RetrievedReferenceLocation


class Attribution(BaseModel):
    citations: Optional[List[Dict[str, Any]]]


class ModelInvocationInput(BaseModel):
    traceId: str
    text: str
    type: str
    inferenceConfiguration: InferenceConfiguration
    overrideLambda: Optional[str] = None
    promptCreationMode: Optional[str] = None
    parserMode: Optional[str] = None


class ModelInvocationOutput(BaseModel):
    traceId: str
    parsedResponse: Dict[str, Any]


class PreProcessingTrace(BaseModel):
    modelInvocationInput: ModelInvocationInput
    modelInvocationOutput: ModelInvocationOutput


class OrchestrationTraceRationale(BaseModel):
    traceId: str
    text: str


class ActionGroupInvocationInputParameter(BaseModel):
    name: str
    type: str
    value: str


class ActionGroupInvocationInputRequestBody(BaseModel):
    content: Dict[str, List[ActionGroupInvocationInputParameter]]


class ActionGroupInvocationInput(BaseModel):
    actionGroupName: str
    apiPath: Optional[str] = None
    executionType: Optional[str] = None
    function: str
    invocationId: Optional[str] = None
    parameters: List[ActionGroupInvocationInputParameter]
    requestBody: Optional[ActionGroupInvocationInputRequestBody] = None
    verb: Optional[str] = None

    @property
    def text(self):
        # Get a string representation of the action group invocation input
        params = ", ".join([f"{p.name}='{p.value}'" for p in self.parameters])
        return f"{self.actionGroupName}.{self.function}({params})"


class KnowledgeBaseLookupInput(BaseModel):
    text: str
    knowledgeBaseId: str


class InvocationInput(BaseModel):
    traceId: str
    invocationType: str
    actionGroupInvocationInput: Optional[ActionGroupInvocationInput] = None
    knowledgeBaseLookupInput: Optional[KnowledgeBaseLookupInput] = None


class FinalResponse(BaseModel):
    text: Optional[str] = None


class KnowledgeBaseLookupOutput(BaseModel):
    retrievedReferences: List[RetrievedReference]


class CodeInterpreterInvocationInput(BaseModel):
    code: str
    files: List[str]


class OrchestrationTraceObservation(BaseModel):
    traceId: str
    type: str
    knowledgeBaseLookupOutput: Optional[KnowledgeBaseLookupOutput] = None
    finalResponse: Optional[FinalResponse] = None
    codeInterpreterInvocationInput: Optional[CodeInterpreterInvocationInput] = None


class OrchestrationTrace(BaseModel):
    rationale: Optional[OrchestrationTraceRationale] = None
    invocationInput: Optional[InvocationInput] = None
    observation: Optional[OrchestrationTraceObservation] = None
    modelInvocationInput: Optional[ModelInvocationInput] = None


class GuardrailTrace(BaseModel):
    traceId: str
    action: str
    # Got lazy here, this should be a more complex structure
    inputAssessments: Optional[List[Dict[str, Any]]] = None
    outputAssessments: Optional[List[Dict[str, Any]]] = None


class Trace(BaseModel):
    preProcessingTrace: Optional[PreProcessingTrace] = None
    orchestrationTrace: Optional[OrchestrationTrace] = None
    guardrailTrace: Optional[GuardrailTrace] = None


class TraceMessage(BaseModel):
    """A simple class to hold a message to be displayed in the Bedrock InvokeAgent response."""
    title: str
    content: Optional[str] = ""


class EventStreamTrace(BaseModel):
    """Bedrock InvokeAgent response traces are a complext nested structure. This class is used to parse the traces."""
    agentId: str
    agentAliasId: str
    sessionId: str
    trace: Trace

    @property
    def messages(self) -> Optional[List[TraceMessage]]:
        """ Helper function to parse the EventStreamTrace and return a TraceMessage object.

        param index: int: The index of the trace message. This will be prefixed to the metadata title.
        return: List[TraceMessage]: List of trace messages or empty list if no message should be displayed.
        """
        messages: List[TraceMessage] = []
        # ORCHESTRATION
        if orchestration_trace := self.trace.orchestrationTrace:
            # RATIONALE
            if orchestration_trace.rationale:
                # The rationale is the reason for the action that is to be taken
                code = orchestration_trace.rationale.text
                messages.append(TraceMessage(content=code, title="rationale"))
            # OBSERVATION
            if orchestration_trace.observation and orchestration_trace.observation.finalResponse:
                # The observation final response is the conclusion of the action taken
                code = orchestration_trace.observation.finalResponse.text
                messages.append(TraceMessage(content=code, title="observation"))
            # CODE INTERPRETER INVOCATION INPUT
            if orchestration_trace.observation and orchestration_trace.observation.codeInterpreterInvocationInput:
                # This should catch created code, but I have never seen this trace hit
                code = orchestration_trace.observation.codeInterpreterInvocationInput.code
                files = ", ".join(orchestration_trace.observation.codeInterpreterInvocationInput.files)
                content = f"```python\n{code}\n```\n\nFiles: {files}\n"
                messages.append(TraceMessage(content=content, title="code input!"))
            # MODEL INVOCATION INPUTS
            if model_invocation_input := orchestration_trace.modelInvocationInput:
                # Check for code blocks in the input text
                for code in [part.split("</code>", 1)[0] for part in model_invocation_input.text.split("<code>")[1:]]:
                    if code != "$CODE":  # This is a placeholder for code in the prompt
                        messages.append(TraceMessage(content=f"```python\n{code}\n```", title="created code"))
            # INVOCATION INPUTS
            if invocation_input := orchestration_trace.invocationInput:
                if action_group_input := invocation_input.actionGroupInvocationInput:
                    # Were calling a tool
                    messages.append(TraceMessage(content=action_group_input.text, title="tool use"))
                if invocation_input.invocationType == "ACTION_GROUP_CODE_INTERPRETER":
                    # We are invoking the code interpreter
                    messages.append(TraceMessage(title="code_interpreter"))
                if invocation_input.invocationType == "KNOWLEDGE_BASE":
                    # We are looking up information in the knowledge base
                    if kb := invocation_input.knowledgeBaseLookupInput:
                        kb_str = f"kb_id:'{kb.knowledgeBaseId}', query:'{kb.text}'"
                        messages.append(TraceMessage(content=kb_str, title="kb_lookup"))
        # GUARDRAIL
        if self.trace.guardrailTrace and self.trace.guardrailTrace.action == "INTERVENED":
            messages.append(TraceMessage(content="guardrail INTERVENED", title="guardrail"))

        # TODO: Memory
        return messages


class EventStreamChunk(BaseModel):
    bytes_: Optional[bytes] = Field(alias="bytes", default=None)
    attribution: Optional[Dict[str, Any]] = None

    @property
    def text(self) -> str:
        if self.bytes_:
            return self.bytes_.decode("utf-8") if self.bytes_ else None
        return ""
