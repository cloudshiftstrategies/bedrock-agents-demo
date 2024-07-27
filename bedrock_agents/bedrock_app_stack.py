import os
import aws_cdk as core
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecr_assets as ecr
from constructs import Construct


class BedrockAppStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, br_agent_id: str, br_agent_alias_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # create function
        code_dir = os.path.join(os.path.dirname(__file__), "..")  # root of this project
        lambda_fn = lambda_.DockerImageFunction(
            self,
            "GradioApp",
            description="Bedrock Agent Function Gradio App",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                file="Dockerfile.ui",
                cmd=["python3", "bedrock_agents/ui/gradio_app.py"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
            ),
            architecture=lambda_.Architecture.X86_64,
            memory_size=8192,
            timeout=core.Duration.minutes(10),
            environment={"BEDROCK_AGENT_ID": br_agent_id, "BEDROCK_AGENT_ALIAS_ID": br_agent_alias_id},
        )
        # Grant the app the ability to invoke the agent
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeAgent"],
                resources=[
                    f"arn:aws:bedrock:{core.Stack.of(self).region}:{core.Stack.of(self).account}:"
                    f"agent-alias/{br_agent_id}/{br_agent_alias_id}"
                ],
            )
        )
        # add HTTPS url
        fn_url = lambda_fn.add_function_url(auth_type=lambda_.FunctionUrlAuthType.NONE, invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM)
        core.CfnOutput(self, "functionUrl", value=fn_url.url)
