import os
from typing import Generator
import gradio as gr
from dotenv import load_dotenv
from gradio_app import helpers, models, kb, oauth_okta, middleware, fixes  # , cw_metrics
import gradio.route_utils

from fastapi import FastAPI, Depends, Request
from starlette.responses import RedirectResponse
from aws_lambda_powertools import Logger
import uvicorn

logger = Logger(service="gradio_app")


load_dotenv()


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
    request_dict = helpers.request_as_dict(request)  # Convert the request object to a dict
    chatbot.append(gr.ChatMessage(role="user", content=prompt))  # Add users prompt text to the chatbot history

    # Before we invoke the agent, Yield the ( chatbot, empty prompt str, request_dict, & events )
    # This puts the user prompt into the chatbot history and empties the prompt textbox
    yield chatbot, "", request_dict, events

    # Send the prompt to the Bedrock agent. The sessionId is the session_hash from the request
    response = helpers.BOTO.bedrock_runtime_client.invoke_agent(
        agentId=os.getenv("BEDROCK_AGENT_ID"),
        agentAliasId=os.getenv("BEDROCK_AGENT_ALIAS_ID"),
        sessionId=request.session_hash,
        endSession=False,
        enableTrace=trace,
        inputText=prompt,
    )

    # Loop through the response chunks (and traces if enableTrace=True) and add them to the chatbot history
    for i, event_chunk in enumerate(response.get("completion")):
        if chunk := event_chunk.get("chunk"):
            # This is a chunk of the AI response, add it to the chatbot history
            chunk = models.EventStreamChunk.model_validate(chunk)
            chatbot.append(gr.ChatMessage(role="assistant", content=chunk.text))

        if event_trace := event_chunk.get("trace"):
            # This is a trace chunk, get the message and add it to chatbot history (if it isnt already there)
            for msg in models.EventStreamTrace.model_validate(event_trace).messages:
                if not any(filter(lambda m: isinstance(m, dict) and m.get("content") == msg.content, chatbot)):
                    metadata = {"title": f"{i}. {msg.title}"}
                    chatbot.append(gr.ChatMessage(role="assistant", content=msg.content, metadata=metadata))

        # Add the raw event chunk to the list of events for debugging
        events.append(event_chunk)
        # For each event chunk, yield the ( chatbot, empty prompt str, request_dict, & events )
        yield chatbot, "", request_dict, events


def get_salutation(request: gr.Request) -> str:
    return f"Welcome {request.username.get('name')}" if request.username else "Welcome"


# This is the entire UI for the Gradio app below
with gr.Blocks(title="Bedrock Agent Demo") as demo:
    with gr.Row():  # Header
        gr.Markdown("# Bedrock Agent Demo")
        salutation = gr.Markdown("Welcome")
        demo.load(get_salutation, outputs=salutation)

    with gr.Tab(label="Chat"):
        chatbot = gr.Chatbot(
            type="messages",  # doesnt work in 4.20
            layout="panel",
            height=800,
            placeholder="Hello, how can I help you?",
            avatar_images=(None, "https://cdn-icons-png.flaticon.com/128/773/773381.png"),
        )
        prompt = gr.Textbox(lines=1, label="Prompt", placeholder="Enter prompt here")
        trace_chkbox = gr.Checkbox(label="Enable", info="Agent Traces", value=True)
        with gr.Accordion(label="Debug", open=False):
            events = gr.JSON(label="Events")  # Shows the raw events for debugging
            request = gr.JSON(label="Request")  # Shows the http request details for debugging
        prompt.submit(
            fn=invoke_agent, inputs=[prompt, chatbot, trace_chkbox], outputs=[chatbot, prompt, request, events]
        )

    with gr.Tab(label="KB"):
        gr.Markdown("Knowledge Base Articles")
        kb_refresh_btn = gr.Button("Refresh Knowledgebase Data", variant="primary")
        kb_file_list = gr.HTML(kb.get_kb_docs)  # List of KB documents in html table
        kb_uploader = gr.File(label="Upload New Article")  # File uploader
        kb_ingestion_jobs_list = gr.DataFrame(kb.get_kb_ingestion_jobs)  # The ingestion jobs table
        kb_uploader.upload(kb.upload_kb_doc, inputs=kb_uploader, outputs=kb_file_list)
        kb_refresh_btn.click(kb.get_kb_ingestion_jobs, outputs=kb_ingestion_jobs_list)
        kb_refresh_btn.click(kb.get_kb_docs, outputs=kb_file_list)

    # with gr.Tab(label="Metrics"):  # TODO this is very slow
    #     gr.Markdown("Bedrock Metrics")
    #     for plot in cw_metrics.get_plots(helpers.BOTO.client("cloudwatch")):
    #         gr.Plot(plot)

app = FastAPI()  # Gradio will be mounted in the FastAPI app as /gradio
gradio.route_utils.get_root_url = fixes.get_root_url  # patch get_root_url() in gradio.route_utils
# Below, `root_path` is non-standard parameter used by monkey patch
app = gr.mount_gradio_app(app, demo, path="/gradio", auth_dependency=oauth_okta.get_user, root_path="/gradio")
app = oauth_okta.init_okta(app)  # Configure the Okta OAuth2 authentication
app.add_middleware(middleware.XForwardedHostMiddleware)  # update host header using X-Forwarded-Host header
app.add_middleware(middleware.LambdaRequestLogger)  # Log the incoming request to debug


@app.get("/")
def public(request: Request, user: dict = Depends(oauth_okta.get_user)):
    """Public route to redirect to login if not authenticated"""
    return RedirectResponse(url="/gradio") if user else RedirectResponse(url="/login")


if __name__ == "__main__":
    uvicorn.run(app, port=int(os.environ.get("PORT", "8080")))  # This is with auth
    # demo.launch(server_port=int(os.environ.get("PORT", "8080")))  # This is without auth
