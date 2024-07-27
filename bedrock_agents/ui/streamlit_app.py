import uuid
import streamlit as st
import boto3
import os
import json

agent_name = "WebSearchAgent"

agent_id = os.environ.get("BEDROCK_AGENT_ID") or "MIKIA04BZU"
agent_alias_id = os.environ.get("BEDROCK_AGENT_ALIAS_ID") or "1LPBUC0GKE"  # LIVE
session = boto3.Session(profile_name="css-lab1")
brart_client = session.client("bedrock-agent-runtime", region_name="us-east-1")

st.title("Bedrock Agent Demo")

prompt = st.chat_input("Ask me anything")

# st.subheader("Output stream", divider="rainbow")

st.session_state["session_id"] = st.session_state.get("session_id") or str(uuid.uuid4())


def parse_stream(stream):
    chunk = stream["chunk"]
    if chunk:
        message = json.loads(chunk.get("bytes").decode())
        if message["type"] == "content_block_delta":
            yield message["delta"]["text"] or ""
        elif message["type"] == "message_stop":
            return "\n"


with st.sidebar:
    st.subheader("Agent Trace")
    trace_placeholder = st.empty()

chat_placeholder = st.empty()

if prompt:
    with st.status("Agent Working...", expanded=True):
        user_message = st.chat_message("user")
        # st.session_state["messages"].append({"user": prompt})
        user_message.write(prompt)
        print(f"User input: '{prompt}'", flush=True)
        trace_placeholder.empty()
        response = brart_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias_id,
            sessionId=st.session_state.get("session_id"),
            endSession=False,
            enableTrace=True,
            inputText=prompt,
        )
        output = ""
        for event in response["completion"]:
            print(".", end="", flush=True)
            if "trace" in event:
                trace = event["trace"].get("trace")
                if "orchestrationTrace" in trace:
                    orchestration_trace = trace["orchestrationTrace"]
                    if rationale := (orchestration_trace.get("rationale") or {}).get("text"):
                        output += f"*Rationale:* {rationale} \n\n----------------\n\n"
                    if observation := ((orchestration_trace.get("observation") or {}).get("finalResponse") or {}).get(
                        "text"
                    ):
                        output += f"*Observation:* {observation} \n\n----------------\n\n"
                    if (
                        action_group_input := (orchestration_trace.get("invocationInput") or {}).get(
                            "actionGroupInvocationInput"
                        )
                        or {}
                    ):
                        action_group_name = action_group_input.get("actionGroupName")
                        function_name = action_group_input.get("function")
                        parameters = action_group_input.get("parameters")
                        parameters = list(map(lambda p: {p["name"], p["value"]}, parameters))
                        function_text = f"{action_group_name}.{function_name} - {parameters}"
                        output += f"*Function:* {function_text} \n\n----------------\n\n"

                    if output:
                        trace_placeholder.markdown(output)
                else:
                    pass

            elif "chunk" in event:
                chunk = event["chunk"]["bytes"].decode("utf-8")
                ai_message = st.chat_message("assistant")
                ai_message.markdown(chunk)
                print(chunk, flush=True)

    print("Done\n-----", flush=True)
