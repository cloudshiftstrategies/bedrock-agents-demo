import os
from typing import Generator
import gradio as gr
import boto3
from dotenv import load_dotenv
from starlette.requests import Request
from bedrock_agents.ui.models import EventStreamChunk, EventStreamTrace

load_dotenv()


class Bedrock:
    # A class to hold the client so that it can be reused
    _client: boto3.client = None
    agent_id = os.environ.get("BEDROCK_AGENT_ID")
    agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID")

    @property
    def client(self):
        if not self._client:
            session = boto3.Session(profile_name=os.getenv("AWS_PROFILE", default=None))
            self._client = session.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION"))
        return self._client


BEDROCK = Bedrock()


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


def invoke_agent(prompt: str, chatbot: gr.Chatbot, trace=False, request: gr.Request = None) -> Generator[any, any, any]:
    """
    Function to interact with the Bedrock agent and return the response
    param prompt: str: The user prompt
    param chatbot: gr.Chatbot: The chatbot object
    param trace: bool: Enable trace. Default is False
    param request: gr.Request: The request object. Populated by Gradio automatically
    return: Generator[any, any, any]: yield ( chatbot, prompt_str, request_dict,  events_list )
    """
    events = []  # empty event list to hold the events for debugging
    request_dict = request_as_dict(request)  # Convert the request object to a dict
    chatbot.append(gr.ChatMessage(role="user", content=prompt))  # Add users prompt text to the chatbot history

    # Before we invoke the agent, Yield the ( chatbot, empty prompt str, request_dict, & events )
    # This puts the user prompt into the chatbot history and empties the prompt textbox
    yield chatbot, "", request_dict, events

    # Send the prompt to the Bedrock agent. The sessionId is the session_hash from the request
    response = BEDROCK.client.invoke_agent(
        agentId=BEDROCK.agent_id,
        agentAliasId=BEDROCK.agent_alias_id,
        sessionId=request.session_hash,
        endSession=False,
        enableTrace=trace,
        inputText=prompt,
    )

    # Loop through the response chunks (and traces if enableTrace=True) and add them to the chatbot history
    for i, event_chunk in enumerate(response.get("completion")):
        if chunk := event_chunk.get("chunk"):
            # This is a chunk of the AI response, add it to the chatbot history
            chunk = EventStreamChunk.model_validate(chunk)
            chatbot.append(gr.ChatMessage(role="assistant", content=chunk.text))

        if event_trace := event_chunk.get("trace"):
            # This is a trace chunk, get the message and add it to chatbot history (if it isnt already there)
            for msg in EventStreamTrace.model_validate(event_trace).messages:
                if not any(filter(lambda m: isinstance(m, dict) and m.get("content") == msg.content, chatbot)):
                    metadata = {"title": f"{i}. {msg.title}"}
                    chatbot.append(gr.ChatMessage(role="assistant", content=msg.content, metadata=metadata))

        # Add the raw event chunk to the list of events for debugging
        events.append(event_chunk)
        # For each event chunk, yield the ( chatbot, empty prompt str, request_dict, & events )
        yield chatbot, "", request_dict, events


# This is the entire UI for the Gradio app below
with gr.Blocks(title="Bedrock Agent Demo") as demo:
    gr.Markdown("# Bedrock Agent Demo")
    chatbot = gr.Chatbot(
        type="messages",
        layout="panel",
        height=1024,
        placeholder="Hello, how can I help you?",
        avatar_images=(None, "https://cdn-icons-png.flaticon.com/128/773/773381.png"),
    )
    prompt = gr.Textbox(lines=1, label="Prompt", placeholder="Enter prompt here")
    trace_checkbox = gr.Checkbox(label="Enable", info="Agent Traces", value=True)
    with gr.Accordion(label="Debug", open=False):
        events = gr.JSON(label="Events")  # Shows the raw events for debugging
        request = gr.JSON(label="Request")  # Shows the http request details for debugging

    # Defines happens when the user submits the prompt - invokes the agent!
    prompt.submit(fn=invoke_agent, inputs=[prompt, chatbot, trace_checkbox], outputs=[chatbot, prompt, request, events])


if __name__ == "__main__":
    demo.launch(debug=True, server_port=8080, show_error=True)
