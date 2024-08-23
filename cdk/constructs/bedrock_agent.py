import os
import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import custom_resources as cr
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ecr_assets as ecr
from constructs import Construct
from cdk.constructs.bedrock_guardrail import BedrockGuardrail
from cdk.stacks.helpers import prune_dir


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
                )
            ],
        )
        self.agent_id = self.agent.attr_agent_id

        # Memory - Will require an AwsCustomResource to enable this
        # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-configure-memory.html


        # Create an Alias for the agent
        self.agent_alias = bedrock.CfnAgentAlias(
            self,
            "Alias",
            agent_id=self.agent.attr_agent_id,
            agent_alias_name="PRODUCTION",
            # Description updates anytime the Agent resource is updated,
            # so that this Alias prepares a new version of the Agent when
            # the Agent changes
            description="Tracking agent timestamp " + self.agent.attr_prepared_at,
        )

        self.agent_alias_id = self.agent_alias.attr_agent_alias_id
        # Ensure agent is fully stabilized before updating the alias
        self.agent_alias.add_dependency(self.agent)

        # local will need these for .env file
        core.CfnOutput(self, "BEDROCK_AGENT_ID", value=self.agent_id)
        core.CfnOutput(self, "BEDROCK_AGENT_VERSION", value=self.agent.attr_agent_version)
        core.CfnOutput(self, "BEDROCK_AGENT_ALIAS_ID", value=self.agent_alias_id)

    def add_code_interpretation(self):
        # Code Interpretation - requires CustomResource to enable this
        # https://docs.aws.amazon.com/bedrock/latest/userguide/agents-enable-code-interpretation.html
        code_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        code_fn = lambda_.DockerImageFunction(
            self,
            "CodeHandler",
            description="Bedrock Agent Code Interpretation Action Group Custom Resource Handler",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                cmd=["cdk.functions.bedrock_agent_code.lambda_handler"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
                exclude=prune_dir(keeps=["functions"]),  # keeps updates smaller and faster
            ),
            timeout=core.Duration.minutes(2),
        )
        code_fn.role.add_to_policy(iam.PolicyStatement(actions=["bedrock:*"], resources=["*"]))  # TODO tighten this up
        code_provider = cr.Provider(
            self,
            "CodeProvider",
            on_event_handler=code_fn,
            log_retention=logs.RetentionDays.ONE_DAY,
        )
        core.CustomResource(
            self,
            "CodeCustomResource",
            service_token=code_provider.service_token,
            resource_type="Custom::BedrockAgentCode",
            properties={
                "agent_id": self.agent_id,
                "agent_alias_name": "PRODUCTION",
            },
        )

    def add_knowledge_base(self, knowledge_base: bedrock.CfnAgent.AgentKnowledgeBaseProperty):
        """Add a knowledge base to the agent"""
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
        """Add an action group to the agent"""
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

    def set_guardrail(self, bedrock_guardrail: BedrockGuardrail):
        """Set the guardrail configuration for the agent"""

        # Add the guardrail to the agent
        self.agent.guardrail_configuration = bedrock_guardrail.agent_configuration

        # Add permission to apply the guardrail
        # https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-permissions.html#guardrails-permissions-invoke
        self.role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:ApplyGuardrail"],
                resources=[
                    f"arn:aws:bedrock:{core.Stack.of(self).region}:{core.Stack.of(self).account}"
                    f":guardrail/{bedrock_guardrail.guardrail.attr_guardrail_id}"
                ],
            )
        )
