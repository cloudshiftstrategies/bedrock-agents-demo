import os
import aws_cdk as core
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecr_assets as ecr
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as sm
from constructs import Construct


class BedrockAppStack(core.Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        br_agent_id: str,
        br_agent_alias_id: str,
        br_kb_bucket: s3.IBucket,
        br_kb_id: str,
        br_datasource_id: str,
        okta_secret: sm.ISecret,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # create function
        code_dir = os.path.join(os.path.dirname(__file__), "..", "..")  # root of this project
        lambda_fn = lambda_.DockerImageFunction(
            self,
            "GradioApp",
            description="Gradio App for Bedrock Agent Demo",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                file="Dockerfile.ui",
                cmd=["python3", "gradio_app/app.py"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
            ),
            architecture=lambda_.Architecture.X86_64,
            memory_size=8192,
            timeout=core.Duration.minutes(10),
            environment={
                "BEDROCK_AGENT_ID": br_agent_id,
                "BEDROCK_AGENT_ALIAS_ID": br_agent_alias_id,
                "KB_BUCKET": br_kb_bucket.bucket_name,
                "KB_ID": br_kb_id,
                "DATASOURCE_ID": br_datasource_id,
                "OKTA_SECRET_ARN": okta_secret.secret_arn,
                "LOG_LEVEL": "DEBUG",
            },
        )
        # Create a function URL to invoke the gratio app function
        fn_url = lambda_fn.add_function_url(
            auth_type=lambda_.FunctionUrlAuthType.NONE, invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM
        )
        core.CfnOutput(self, "gradioUrl", value=fn_url.url)

        # Allow the app to read/write to the kb bucket.
        # Normally we wouldnt allow users to update the kb, but this is only for the demo
        br_kb_bucket.grant_read_write(lambda_fn)

        # Allow the app to read the Okta secret
        okta_secret.grant_read(lambda_fn)

        # Grant the gradio app the ability to invoke the bedrock agent
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeAgent"],
                resources=[
                    f"arn:aws:bedrock:{core.Stack.of(self).region}:{core.Stack.of(self).account}:"
                    f"agent-alias/{br_agent_id}/{br_agent_alias_id}"
                ],
            )
        )
        # Grant the gradio app the ability to invoke list_ingestion_jobs
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["bedrock:ListIngestionJobs"],
                resources=["*"],
            )
        )
        # Allow the function to call cloudwatch list_metrics and get_metric_data
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:ListMetrics", "cloudwatch:GetMetricData"],
                resources=["*"],
            )
        )
