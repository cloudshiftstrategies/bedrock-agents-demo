import json
import aws_cdk as core
import os
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import custom_resources as cr
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_ecr_assets as ecr
from cdk.functions import pinecone_index as pi_fn
from constructs import Construct

from cdk.stacks.helpers import prune_dir


class PineconeSecret(Construct):
    def __init__(self, scope: Construct, id: str):
        super().__init__(scope, id)
        self.secret = sm.Secret(
            self,
            "Secret",
            description="Pinecone index API Key",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template=json.dumps({"apiKey": "CHANGE_ME"}),
                generate_string_key="apiKey",
            ),
            removal_policy=core.RemovalPolicy.DESTROY,
        )
        core.CfnOutput(self, "SecretArn", value=self.secret.secret_arn)


class PinconeIndex(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        secret: PineconeSecret,
        dimension=pi_fn.DEFAULT_DIMENSION,
        metric=pi_fn.DEFAULT_METRIC,
        cloud=pi_fn.DEFAULT_CLOUD,
        region=pi_fn.DEFAULT_REGION,
    ):
        super().__init__(scope, id)

        # If name has any uppercase characters, raise an error
        if any(c.isupper() for c in name):
            raise ValueError("PinconeIndex name must be lowercase")

        self.secret = secret

        # Create a docker based lambda function that can manage the pinecone index (create, delete, etc.)
        code_dir = os.path.join(os.path.dirname(__file__), "..", "..")  # root of this project
        self.handler = lambda_.DockerImageFunction(
            self,
            "Handler",
            description="Pinecone Index Custom Resource Handler",
            code=lambda_.DockerImageCode.from_image_asset(
                directory=code_dir,
                cmd=["cdk.functions.pinecone_index.lambda_handler"],
                platform=ecr.Platform.LINUX_AMD64,  # required when building on arm64 machines (mac m1)
                exclude=prune_dir(keeps=["functions", "models"]),  # keeps updates smaller and faster
            ),
            timeout=core.Duration.minutes(2),
            environment={pi_fn.PINECONE_API_KEY_SECRET_ENV_NAME: self.secret.secret_name},
        )
        self.secret.grant_read(self.handler)

        # Custom resource provider
        self.provider = cr.Provider(
            self,
            "Provider",
            on_event_handler=self.handler,
        )

        # The Pinecone index custom resource
        self.index = core.CustomResource(
            self,
            "CustomResource",
            resource_type="Custom::PineconeIndex",
            service_token=self.provider.service_token,
            properties={
                "name": name,
                "dimension": dimension,
                "metric": metric,
                "cloud": cloud,
                "region": region,
            },
        )
        # Set the properties on the index for easy access
        self.name = self.index.get_att("name").to_string()
        self.host = self.index.get_att("host").to_string()
        self.dimension = self.index.get_att("dimension").to_string()
        self.metric = self.index.get_att("metric").to_string()
        self.region = self.index.get_att("spec.region").to_string()
        self.cloud = self.index.get_att("spec.cloud").to_string()

        core.CfnOutput(self, "PineconeHost", value="https://" + self.host)
