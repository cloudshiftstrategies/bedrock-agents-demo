import os
import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ecr_assets as ecr
from constructs import Construct
from cdk.constructs import pinecone_index as pi
from cdk.constructs.bedrock_agent import BedrockAgent
from cdk.constructs.bedrock_guardrail import BedrockGuardrail
from cdk.constructs.bedrock_pinecone_knowledgebase import BedrockPineconeKnowledgeBase
from cdk.stacks.helpers import prune_dir


class BedrockAgentsStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, secret: pi.PineconeSecret, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Agent
        self.bedrock_agent = BedrockAgent(
            self,
            "BedrockDemoAgent",
            agent_name="BedrockDemoAgent",
            agent_description="General purpose agent that can answer a variety of questions.",
            agent_instruction="You are a helful agent who can solve all kinds of problems for the user. "
            "Use your knowledgebases and any availible tool to search for the best answers to the users question. "
            "Always respond to the user in markdown format, especially code blocks.",
            # Supported models https://docs.aws.amazon.com/bedrock/latest/userguide/agents-supported.html
            agent_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        )

        # Knowledge Base
        self.knowledge_base = BedrockPineconeKnowledgeBase(
            self,
            "BedrockDemoKb",
            name="BedrockDemoKb",
            description="Bedrock Demo Agent Knowledge Base",
            pinecone_secret=secret,
        )
        self.bedrock_agent.add_knowledge_base(
            bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowlegdebase for contracts and documents are private and wont be found online",
                knowledge_base_id=self.knowledge_base.knowledge_base.attr_knowledge_base_id,
            )
        )

        # Web Search Tool
        code_dir = os.path.join(os.path.dirname(__file__), "..", "..")  # root of this project
        web_search_fn = lambda_.DockerImageFunction(
            self,
            "WebSearchTool",
            description="Web Search Tool for Bedrock Agent",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                cmd=["cdk.functions.web_search.lambda_handler"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
                exclude=prune_dir(keeps=["functions", "models"]),  # keeps updates smaller and faster
            ),
            timeout=core.Duration.seconds(60),
            memory_size=1024,
            environment={"SECRET_NAME": secret.secret_name},
        )
        self.bedrock_agent.add_action_group(
            bedrock.CfnAgent.AgentActionGroupProperty(
                action_group_name="web_search",
                description="Conducts web searches and retrieves information from web urls.",
                skip_resource_in_use_check_on_delete=True,
                action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(lambda_=web_search_fn.function_arn),
                function_schema=bedrock.CfnAgent.FunctionSchemaProperty(
                    functions=[
                        bedrock.CfnAgent.FunctionProperty(
                            name="search",
                            description="Search the web for information",
                            parameters={
                                "query": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",  # "string" | number | integer | boolean | array,
                                    description="the query to search for",
                                    required=True,
                                )
                            },
                        ),
                        bedrock.CfnAgent.FunctionProperty(
                            name="retrieve",
                            description="Retrieve information from a web url",
                            parameters={
                                "url": bedrock.CfnAgent.ParameterDetailProperty(
                                    type="string",
                                    description="url to retrieve information from",
                                    required=True,
                                )
                            },
                        ),
                    ]
                ),
            )
        )

        # Guardrail
        self.guardrail = BedrockGuardrail(
            self,
            "BedrockDemoGuardrail",
            name="BedrockDemoGuardrail",
            description="Guardrail to protect BedrockDemoAgent",
            sensitive_information_policy_config=bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty(
                # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-bedrock-guardrail-piientityconfig.html
                pii_entities_config=[
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(action="ANONYMIZE", type="EMAIL"),  # Sanitize email
                    bedrock.CfnGuardrail.PiiEntityConfigProperty(action="BLOCK", type="PASSWORD"),  # Block passwords
                ],
            ),
        )
        self.bedrock_agent.set_guardrail(self.guardrail)

        # bucket used to store user files
        self.code_bucket = s3.Bucket(
            self, "BedrockDemoCodeBucket", removal_policy=core.RemovalPolicy.DESTROY, auto_delete_objects=True
        )
        self.code_bucket.grant_read(self.bedrock_agent.role)
