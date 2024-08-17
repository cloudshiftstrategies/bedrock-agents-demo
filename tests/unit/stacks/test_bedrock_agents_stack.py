# example tests. To run these tests, uncomment this file along with the example
# resource in bedrock_agents/bedrock_agents_stack.py
# def test_agent_stack():
#     app = core.App()
#     stack = BedrockAgentsStack(app, "bedrock-agents")
#     template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
