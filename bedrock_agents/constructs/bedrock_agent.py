import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import custom_resources as cr
from constructs import Construct


class BedrockAgent(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        agent_name: str,
        agent_description: str,
        agent_instruction: str,
        agent_model_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.role = iam.Role(
            self,
            "Role",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Role for the Test Bedrock Agent",
        )
        # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html#agents-permissions-identity
        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[f"arn:aws:bedrock:{core.Stack.of(self).region}::foundation-model/{agent_model_id}"],
            )
        )
        self.agent = bedrock.CfnAgent(
            self,
            "Resource",
            agent_name=agent_name,
            description=agent_description,
            instruction=agent_instruction,
            foundation_model=agent_model_id,
            agent_resource_role_arn=self.role.role_arn,
            skip_resource_in_use_check_on_delete=True,
            auto_prepare=True,  # automatically update the DRAFT version of the agent after making changes
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    # Allow the agent to request user input
                    action_group_name="user_input",
                    parent_action_group_signature="AMAZON.UserInput",
                ),
            ],
        )
        self.agent_id = self.agent.attr_agent_id

        # Memory - Will require an AwsCustomResource to enable this
        # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-configure-memory.html

        # Code Interpretation - Will require AwsCustomResource to enable this
        # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html
        cr.AwsCustomResource(
            self,
            "AgentCodeInterpreter",
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE),
            on_create=cr.AwsSdkCall(
                service="bedrock-agent",
                action="CreateAgentActionGroup",
                parameters={
                    "agentId": self.agent.attr_agent_id,
                    "agentVersion": self.agent.attr_agent_version,
                    "actionGroupName": "code_interpreter",
                    "parentActionGroupSignature": "AMAZON.CodeInterpreter",
                    "actionGroupState": "ENABLED",
                },
                physical_resource_id=cr.PhysicalResourceId.from_response("agentActionGroup.actionGroupId"),
            ),
        )

        self.agent_alias = bedrock.CfnAgentAlias(
            self,
            "Alias",
            agent_id=self.agent.attr_agent_id,
            agent_alias_name="LIVE",
            # Description updates anytime the Agent resource is updated,
            # so that this Alias prepares a new version of the Agent when
            # the Agent changes
            description="Tracking agent timestamp " + self.agent.attr_prepared_at,
        )
        self.agent_alias_id = self.agent_alias.attr_agent_alias_id
        # Ensure agent is fully stabilized before updating the alias
        self.agent_alias.add_dependency(self.agent)

    def add_knwledge_base(self, knowledge_base: bedrock.CfnAgent.AgentKnowledgeBaseProperty):
        kbs = self.agent.knowledge_bases or []
        kbs.append(knowledge_base)
        self.agent.knowledge_bases = kbs
        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"],
                resources=[
                    f"arn:aws:bedrock:{core.Stack.of(self).region}:{core.Stack.of(self).account}"
                    f":knowledge-base/{knowledge_base.knowledge_base_id}"
                ],
            )
        )

    def add_action_group(self, action_group: bedrock.CfnAgent.AgentActionGroupProperty):
        ags = self.agent.action_groups or []
        ags.append(action_group)
        self.agent.action_groups = ags
        if action_group.action_group_executor.lambda_:
            # Create a lambda resource policy that grants the agent permission to invoke the lambda function
            # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-permissions.html#agents-permissions-lambda
            lambda_.CfnPermission(
                self,
                "InvokePermission",
                action="lambda:InvokeFunction",
                function_name=action_group.action_group_executor.lambda_,
                principal="bedrock.amazonaws.com",
                source_arn=self.agent.attr_agent_arn,
            )
