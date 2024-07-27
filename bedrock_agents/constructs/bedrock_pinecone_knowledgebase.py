import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from bedrock_agents.constructs import pinecone_index as pi
from constructs import Construct


class BedrockPineconeKnowledgeBase(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        description: str,
        pinecone_secret: pi.PineconeSecret,
        embedding_model_id="amazon.titan-embed-text-v2:0",
        dimension=1024,
        chunking_strategy="FIXED_SIZE",
        max_tokens=1000,
        overlap_percentage=20,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.role = iam.Role(self, "Role", assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"))
        embedding_model_arn = f"arn:aws:bedrock:{core.Stack.of(self).region}::foundation-model/{embedding_model_id}"
        self.role.add_to_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn]))

        self.pinecone_index = pi.PinconeIndex(
            self, "PineconeIndex", name=name.lower(), secret=pinecone_secret, dimension=dimension
        )
        self.pinecone_index.secret.grant_read(self.role)

        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "Resource",
            name=name,
            description=description,
            role_arn=self.role.role_arn,  # must have access to the pinecone secret
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_arn
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="PINECONE",
                pinecone_configuration=bedrock.CfnKnowledgeBase.PineconeConfigurationProperty(
                    connection_string="https://" + self.pinecone_index.host,
                    credentials_secret_arn=self.pinecone_index.secret.secret_arn,
                    field_mapping=bedrock.CfnKnowledgeBase.PineconeFieldMappingProperty(
                        metadata_field="metadataField", text_field="textField"
                    ),
                ),
            ),
        )

        # Create an S3 bucket to store the recipe pdfs
        # TODO: Create a lamdba function to sync the s3 bucket with the knowledge base on changes
        self.bucket = s3.Bucket(
            self,
            "Bucket",
            auto_delete_objects=True,
            removal_policy=core.RemovalPolicy.DESTROY,
        )
        self.bucket.grant_read(self.role)
        self.data_source = bedrock.CfnDataSource(
            self,
            "DataSource",
            name=name,
            description=description,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.bucket.bucket_arn,
                    # inclusion_prefixes=["inclusionPrefixes"] # Optional
                ),
                type="S3",
            ),
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            # the properties below are optional
            data_deletion_policy="DELETE",  # or "RETAIN" # The data deletion policy for a data source.
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    # https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-bedrock-datasource-chunkingconfiguration.html
                    # chunking_strategy="NONE", # NONE (whole file)
                    # the properties below are only required if chunking_strategy is FIXED_SIZE
                    chunking_strategy=chunking_strategy,  # FIXED_SIZE split as per `fixed_size_chunking_configuration``
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=max_tokens,  # Maximum number of tokens per chunk
                        overlap_percentage=overlap_percentage,  # Percentage of overlap between chunks
                    ),
                )
            ),
        )
