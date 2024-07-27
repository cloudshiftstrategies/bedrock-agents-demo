import os
import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3_deployment
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecr_assets as ecr
from constructs import Construct
from bedrock_agents.constructs import pinecone_index as pi
from bedrock_agents.constructs.bedrock_agent import BedrockAgent
from bedrock_agents.constructs.bedrock_pinecone_knowledgebase import BedrockPineconeKnowledgeBase


class BedrockAgentsStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, secret: pi.PineconeSecret, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        knowledge_base = BedrockPineconeKnowledgeBase(
            self,
            "KnowledgeBase",
            name="BedrockAgentsKb",
            description="Bedrocks Agents Testing Knowledge Base",
            pinecone_secret=secret,
        )

        # Deploy the recipe pdfs to s3 bucket
        s3_deployment.BucketDeployment(
            self,
            "RecipeDeployment",
            sources=[
                s3_deployment.Source.asset(
                    "/Users/brianpeterson/dropbox/Recipes/",
                    follow_symlinks=core.SymlinkFollowMode.ALWAYS,
                )
            ],
            destination_bucket=knowledge_base.bucket,
            exclude=[".DS_Store"],
            memory_limit=1024,  # increase memory to avoid sigkill.9 errors on large uploads
        )

        code_dir = os.path.join(os.path.dirname(__file__), "..")  # root of this project
        web_search_fn = lambda_.DockerImageFunction(
            self,
            "WebSearchFunction",
            description="Bedrock Agent Function Web Search",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                cmd=["bedrock_agents.functions.web_search.lambda_handler"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
            ),
            timeout=core.Duration.seconds(60),
            memory_size=1024,
            environment={"SECRET_NAME": secret.secret_name},
        )

        self.bedrock_agent = BedrockAgent(
            self,
            "BedrockAgent",
            agent_name="WebSearchAgent",
            agent_description="Agent to search the web for information",
            agent_instruction="You are a helful agent who can solve all kinds of problems for the user. "
            "Use your knowledges and tools to search the web for information. "
            "Always respond to the user in markdown format, especially code blocks.",
            # Supported models https://docs.aws.amazon.com/bedrock/latest/userguide/agents-supported.html
            agent_model_id="anthropic.claude-3-sonnet-20240229-v1:0",
        )
        self.bedrock_agent.add_knwledge_base(
            bedrock.CfnAgent.AgentKnowledgeBaseProperty(
                description="Knowledge base for the agent",
                knowledge_base_id=knowledge_base.knowledge_base.attr_knowledge_base_id,
            )
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

        # This bucket will be used to upload code for the agent
        code_bucket = s3.Bucket(self, "CodeBucket", removal_policy=core.RemovalPolicy.DESTROY, auto_delete_objects=True)
        self.bedrock_agent.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetObjectVersionAttributes",
                    "s3:GetObjectAttributes",
                ],
                resources=[code_bucket.bucket_arn + "/*"],
            )
        )
