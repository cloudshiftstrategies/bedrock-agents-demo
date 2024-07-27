import aws_cdk as core
from constructs import Construct
from bedrock_agents.constructs import pinecone_index as pi


class BedrockDataStack(core.Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.secret = pi.PineconeSecret(self, "PineconeApi").secret
