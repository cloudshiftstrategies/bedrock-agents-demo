import aws_cdk as core
import aws_cdk.assertions as assertions

from bedrock_agents.bedrock_agents_stack import BedrockAgentsStack

# example tests. To run these tests, uncomment this file along with the example
# resource in bedrock_agents/bedrock_agents_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = BedrockAgentsStack(app, "bedrock-agents")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
