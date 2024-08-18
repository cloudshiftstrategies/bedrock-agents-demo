from textwrap import dedent
import aws_cdk as core
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_lambda as lambda_
from cdk.constructs import pinecone_index as pi
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

        embedding_model_arn = f"arn:aws:bedrock:{core.Stack.of(self).region}::foundation-model/{embedding_model_id}"

        # This is the role that the knowledge base will assume
        self.kb_role = iam.Role(self, "Role", assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"))
        self.kb_role.add_to_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=[embedding_model_arn])
        )

        # Create a pinecone index
        self.pinecone_index = pi.PinconeIndex(
            self, "PineconeIndex", name=name.lower(), secret=pinecone_secret, dimension=dimension
        )
        self.pinecone_index.secret.grant_read(self.kb_role)

        # Create a knowledge base
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "Resource",
            name=name,
            description=description,
            role_arn=self.kb_role.role_arn,  # must have access to the pinecone secret
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
        self.knowledge_base_id = self.knowledge_base.attr_knowledge_base_id

        # Create an S3 bucket to store the kb articles
        self.bucket = s3.Bucket(
            self,
            "Bucket",
            auto_delete_objects=True,
            removal_policy=core.RemovalPolicy.DESTROY,
        )

        # configure CORS policy on bucket to allow presigned urls to get and delete objects
        # This is only allowed do that the gradio app can use presigned urls to manage the data
        self.bucket.add_cors_rule(
            allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.POST, s3.HttpMethods.DELETE],
            allowed_origins=["*"],
            allowed_headers=["*"],
            max_age=3000,
        )
        self.bucket.grant_read(self.kb_role)

        # Create a data source for the knowledge base from s3 bucket
        self.data_source = bedrock.CfnDataSource(
            self,
            "DataSource",
            name=name,
            description=description,
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=self.bucket.bucket_arn,
                ),
                type="S3",
            ),
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            # the properties below are optional
            data_deletion_policy="RETAIN",  # We can let cloudformation handle the deletion of the vector db
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
        self.data_source_id = self.data_source.attr_data_source_id

        # Create a lambda function to start ingestion job when new data is added or deleted from the bucket
        self.ingestion_fn = lambda_.Function(
            self,
            "IngestionFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="index.handler",
            code=lambda_.Code.from_inline(
                dedent(
                    """
            import os, boto3, logging, json

            logger = logging.getLogger()
            logger.setLevel(logging.INFO)
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(json.dumps({
                "timestamp": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s",
                "logger": "%(name)s", "pathname": "%(pathname)s", "lineno": "%(lineno)d", "funcName": "%(funcName)s"
            })))
            logger.addHandler(handler)

            def handler(event, context):
                logger.info(json.dumps({"event": event}))
                event_records = event.get("Records", [])
                triggers = ", ".join([f"{r['eventName']} - {r['s3']['object']['key']}" for r in event_records])
                logger.info(f"Starting ingestion job, datasource:{os.getenv('DATASOURCE_ID')}, kb:{os.getenv('KB_ID')}")
                result = boto3.client("bedrock-agent").start_ingestion_job(
                    dataSourceId=os.getenv("DATASOURCE_ID"),
                    knowledgeBaseId=os.getenv("KB_ID"),
                    description=f"s3 trigger: {triggers}"
                )
                logger.info(f"Started ingestion job: {result.get('ingestionJob').get('ingestionJobId')}")
            """
                )
            ),
            environment={
                "DATASOURCE_ID": self.data_source.attr_data_source_id,
                "KB_ID": self.knowledge_base.attr_knowledge_base_id,
            },
        )
        self.ingestion_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:StartIngestionJob", "bedrock:AssociateThirdPartyKnowledgeBase"],
                resources=[self.knowledge_base.attr_knowledge_base_arn],
            )
        )
        self.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.ingestion_fn),
        )
        self.bucket.add_event_notification(
            s3.EventType.OBJECT_REMOVED,
            s3n.LambdaDestination(self.ingestion_fn),
        )
        # Local user will need these for .env file
        core.CfnOutput(self, "KB_BUCKET", value=self.bucket.bucket_name)
        core.CfnOutput(self, "KB_ID", value=self.knowledge_base.attr_knowledge_base_id)
        core.CfnOutput(self, "DATASOURCE_ID", value=self.data_source.attr_data_source_id)
