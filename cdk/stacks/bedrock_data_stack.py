import aws_cdk as core
from constructs import Construct
from cdk.constructs import pinecone_index as pi
from aws_cdk import aws_secretsmanager as sm
import json


class BedrockDataStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.secret = pi.PineconeSecret(self, "PineconeApi").secret
        # Create a Secret for Okta credentials
        self.okta_secret = sm.Secret(
            self,
            "OktaSecret",
            description=f"Okta secret for stack: {core.Stack.of(self).stack_name}",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template=json.dumps(
                    {
                        "OKTA_OAUTH2_ CLIENT_ID": "CHANGE_ME",
                        "OKTA_OAUTH2_CLIENT_SECRET": "CHANGE_ME",
                        "OKTA_OAUTH2_ISSUER": "CHANGE_ME",
                        "SESSION_SECRET": "PASSWORD",
                    }
                ),
                generate_string_key="SESSION_SECRET",
            ),
            removal_policy=core.RemovalPolicy.DESTROY,
        )
        core.CfnOutput(self, "OktaSecretArn", value=self.okta_secret.secret_arn)
