import os
import uuid
import gradio as gr
import boto3
from dotenv import load_dotenv
from starlette.requests import Request

load_dotenv()
AGENT_ID = os.environ.get("BEDROCK_AGENT_ID")
AGENT_ALIAS_ID = os.environ.get("BEDROCK_AGENT_ALIAS_ID")


def get_client():
    session = boto3.Session(profile_name=os.getenv("AWS_PROFILE", default=None))
    return session.client("bedrock-agent-runtime", region_name=os.environ.get("AWS_REGION"))


def get_request_dict(request: Request) -> dict:
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


def bedrock_agent(prompt, chatbot, trace=False, request: gr.Request = None):
    chatbot.append(gr.ChatMessage(role="user", content=prompt))
    yield chatbot, "", get_request_dict(request)

    brart_client = get_client()
    response = brart_client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=request.session_hash,
        endSession=False,
        enableTrace=trace,
        inputText=prompt,
    )
    for event in response["completion"]:
        if "chunk" in event:
            # This is a chunk of the actual response
            chunk = event["chunk"]["bytes"].decode("utf-8")
            chatbot.append(gr.ChatMessage(role="assistant", content=chunk))
        if trace and "trace" in event:
            # This is a trace event
            trace = event["trace"].get("trace")
            if "orchestrationTrace" in trace:
                orchestration_trace = trace["orchestrationTrace"]
                if rationale := (orchestration_trace.get("rationale") or {}).get("text"):
                    chatbot.append(gr.ChatMessage(role="assistant", content=rationale, metadata={"title": "rationale"}))
                if observation := ((orchestration_trace.get("observation") or {}).get("finalResponse") or {}).get(
                    "text"
                ):
                    chatbot.append(
                        gr.ChatMessage(role="assistant", content=observation, metadata={"title": "observation"})
                    )
                if (
                    action_group_input := (orchestration_trace.get("invocationInput") or {}).get(
                        "actionGroupInvocationInput"
                    )
                    or {}
                ):
                    action_group_name = action_group_input.get("actionGroupName")
                    function_name = action_group_input.get("function")
                    parameters = list(map(lambda p: {p["name"], p["value"]}, action_group_input.get("parameters")))
                    function_text = f"{action_group_name}.{function_name}({parameters})"
                    chatbot.append(gr.ChatMessage(role="assistant", content=function_text, metadata={"title": "tool"}))
        yield chatbot, "", get_request_dict(request)


with gr.Blocks(title="Bedrock Agent Demo") as demo:
    gr.Markdown("# Bedrock Agent Demo")
    chatbot = gr.Chatbot(
        type="messages",
        label="Bedrock Agent Chat",
        avatar_images=(None, "https://cdn-icons-png.flaticon.com/128/773/773381.png"),
    )
    prompt = gr.Textbox(lines=1, label="Prompt", min_width=1200)
    trace = gr.Checkbox(label="Enable Trace", container=False)
    with gr.Accordion("Debug", open=False):
        request = gr.JSON(label="Request")
    prompt.submit(fn=bedrock_agent, inputs=[prompt, chatbot, trace], outputs=[chatbot, prompt, request])

if __name__ == "__main__":
    demo.launch(debug=True, server_port=8080, show_error=True)
