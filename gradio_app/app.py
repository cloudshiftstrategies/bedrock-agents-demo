from typing import Generator
import gradio as gr
from dotenv import load_dotenv
from gradio_app import cw_metrics, helpers, kb, models


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
        agentId=helpers.BOTO.agent_id,
        agentAliasId=helpers.BOTO.agent_alias_id,
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


# This is the entire UI for the Gradio app below
with gr.Blocks(title="Bedrock Agent Demo") as demo:
    gr.Markdown("# Bedrock Agent Demo")
    with gr.Tab(label="Chat"):
        chatbot = gr.Chatbot(
            type="messages",
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
    with gr.Tab(label="KB"):
        gr.Markdown("Knowledge Base Articles")
        file_list = gr.HTML(kb.get_kb_docs)  # List of KB documents in html table
        kb_file = gr.File(label="Upload New Article")  # File uploader
        with gr.Accordion(label="Ingestion Jobs", open=True):
            refresh_jobs_btn = gr.Button("Refresh Ingestion Job List", variant="primary")  # Button to refresh jobs
            ingestion_jobs = gr.DataFrame(kb.get_kb_ingestion_jobs)  # The ingestion jobs table
    with gr.Tab(label="Metrics"):
        gr.Markdown("Bedrock Metrics")
        for plot in cw_metrics.get_plots(helpers.BOTO.client("cloudwatch")):
            gr.Plot(plot)

    # Events and Actions
    prompt.submit(fn=invoke_agent, inputs=[prompt, chatbot, trace_chkbox], outputs=[chatbot, prompt, request, events])
    kb_file.upload(kb.upload_kb_doc, inputs=kb_file, outputs=file_list)  # Upload a new document to the KB
    refresh_jobs_btn.click(kb.get_kb_ingestion_jobs, outputs=ingestion_jobs)  # Refresh jobs table when clicked

if __name__ == "__main__":
    demo.launch(debug=True, server_port=8080, show_error=True)
