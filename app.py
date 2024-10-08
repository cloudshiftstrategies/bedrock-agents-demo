#!/usr/bin/env python3

import aws_cdk as core

from cdk.stacks.bedrock_agents_stack import BedrockAgentsStack
from cdk.stacks.bedrock_data_stack import BedrockDataStack
from cdk.stacks.bedrock_app_stack import BedrockAppStack


env = core.Environment(account="603006933259", region="us-east-1")
app = core.App()
data_stack = BedrockDataStack(app, "BedrockDataStack-testing", description="Bedrock Test Data", env=env)
agent_stack = BedrockAgentsStack(
    app,
    "BedrockAgentsStack-testing",
    description="Bedrock Agents",
    secret=data_stack.secret,
    env=env,
)
app_stack = BedrockAppStack(
    app,
    "BedrockAppStack-testing",
    description="Bedrock App",
    br_agent_id=agent_stack.bedrock_agent.agent_id,
    br_agent_alias_id=agent_stack.bedrock_agent.agent_alias_id,
    br_kb_bucket=agent_stack.knowledge_base.bucket,
    br_kb_id=agent_stack.knowledge_base.knowledge_base_id,
    br_datasource_id=agent_stack.knowledge_base.data_source_id,
    okta_secret=data_stack.okta_secret,
    env=env,
)

# Force the dependency between the stacks
agent_stack.add_dependency(data_stack)
app_stack.add_dependency(data_stack)

app.synth()
