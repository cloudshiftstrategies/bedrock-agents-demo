import os
import aws_cdk as core
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import aws_ecr_assets as ecr
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_route53 as r53
from aws_cdk import aws_route53_targets as r53_targets
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_secretsmanager as sm
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
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
        host_name = "bedrock-demo"
        zone_name = "css-lab1.cloudshift.cc"
        fqdn = f"{host_name}.{zone_name}"

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
                "HOST_NAME": f"https://{fqdn}",
                "LOG_LEVEL": "DEBUG",
            },
        )

        # Allow app to read/write to the kb bucket so we can maintain the kb from the app
        br_kb_bucket.grant_read_write(lambda_fn)

        # Allow app to read the Okta secret
        okta_secret.grant_read(lambda_fn)

        # Grant app the ability to invoke the bedrock agent
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeAgent"],
                resources=[
                    f"arn:aws:bedrock:{core.Stack.of(self).region}:{core.Stack.of(self).account}:"
                    f"agent-alias/{br_agent_id}/{br_agent_alias_id}"
                ],
            )
        )
        # Allow app to list_ingestion_jobs
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["bedrock:ListIngestionJobs"],
                resources=["*"],
            )
        )
        # Allow app to call cloudwatch list_metrics and get_metric_data
        lambda_fn.role.add_to_principal_policy(
            iam.PolicyStatement(
                actions=["cloudwatch:ListMetrics", "cloudwatch:GetMetricData"],
                resources=["*"],
            )
        )

        # Create a function URL to invoke the gratio app function
        fn_url = lambda_fn.add_function_url(
            # https://aws.amazon.com/blogs/networking-and-content-delivery/secure-your-lambda-function-urls-using-amazon-cloudfront-origin-access-control/
            # auth_type=lambda_.FunctionUrlAuthType.AWS_IAM,
            auth_type=lambda_.FunctionUrlAuthType.NONE,
            invoke_mode=lambda_.InvokeMode.RESPONSE_STREAM,
            cors=lambda_.FunctionUrlCorsOptions(
                allowed_origins=["*"],
                allowed_methods=[lambda_.HttpMethod.GET, lambda_.HttpMethod.POST],
                allow_credentials=True,
                max_age=core.Duration.minutes(1),
            ),
        )
        core.CfnOutput(self, "GradioFnUrl", value=fn_url.url)

        # CLOUDFRONT DISTRIBUTION

        # Extract the function domain name (<domain_name>) from the function URL (https://<domain_name>/)
        fn_domain_name = core.Fn.select(2, core.Fn.split("/", fn_url.url))

        # Create an SSL certificate in ACM for the domain
        zone = r53.HostedZone.from_lookup(self, "HostedZone", domain_name=zone_name)
        certificate = acm.Certificate(
            self,
            "Cert",
            domain_name=fqdn,
            validation=acm.CertificateValidation.from_dns(hosted_zone=zone),
        )

        # Create a Lambda function to rewrite the host header to x-forwarded-host
        cf_host_rw_fn = cf.Function(
            self,
            "RewriteCdnHost",
            comment="Copy host header to x-forwarded-host",
            code=cf.FunctionCode.from_inline(
                """
                function handler(event) {
                    var req = event.request;
                    if (req.headers['host']) { req.headers['x-forwarded-host'] = {value: req.headers['host'].value}; }
                    return req;
                }
            """
            ),
        )
        # Create a bucket for CloudFront logs
        cf_log_bucket = s3.Bucket(
            self,
            "cloudfrontLogBucket",
            access_control=s3.BucketAccessControl.LOG_DELIVERY_WRITE,
            object_ownership=s3.ObjectOwnership.OBJECT_WRITER,
            removal_policy=core.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        cf_log_bucket.add_lifecycle_rule(enabled=True, expiration=core.Duration.days(30))

        # Create a CloudFront distribution
        cdn = cf.Distribution(
            self,
            "MyDistribution",
            domain_names=[fqdn],
            certificate=certificate,
            price_class=cf.PriceClass.PRICE_CLASS_100,
            http_version=cf.HttpVersion.HTTP2,
            log_bucket=cf_log_bucket,
            default_behavior=cf.BehaviorOptions(
                origin=origins.HttpOrigin(
                    domain_name=fn_domain_name,
                    protocol_policy=cf.OriginProtocolPolicy.HTTPS_ONLY,
                    origin_ssl_protocols=[cf.OriginSslPolicy.TLS_V1_2],
                ),
                allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                cached_methods=cf.CachedMethods.CACHE_GET_HEAD_OPTIONS,
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                compress=True,
                smooth_streaming=True,
                # origin_request_policy=cf.OriginRequestPolicy.CORS_CUSTOM_ORIGIN,
                cache_policy=cf.CachePolicy(
                    self,
                    "CachePolicy",
                    header_behavior=cf.CacheHeaderBehavior.allow_list("Authorization", "X-Forwarded-Host"),
                    cookie_behavior=cf.CacheCookieBehavior.allow_list("session"),
                    query_string_behavior=cf.CacheQueryStringBehavior.all(),
                    max_ttl=core.Duration.hours(1),
                    min_ttl=core.Duration.seconds(300),
                    default_ttl=core.Duration.seconds(300),
                    enable_accept_encoding_gzip=True,
                    enable_accept_encoding_brotli=True,
                ),
                # cache_policy=cf.CachePolicy.CACHING_DISABLED,
                response_headers_policy=cf.ResponseHeadersPolicy.SECURITY_HEADERS,
                function_associations=[
                    cf.FunctionAssociation(
                        event_type=cf.FunctionEventType.VIEWER_REQUEST,
                        function=cf_host_rw_fn,
                    )
                ],
            ),
        )

        # Create an Origin Access Control for the Lambda function
        oac = cf.CfnOriginAccessControl(
            self,
            "GradioLambdaOAC",
            origin_access_control_config=cf.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name="GradioLambdaOAC",
                origin_access_control_origin_type="lambda",
                signing_behavior="always",
                signing_protocol="sigv4",
            ),
        )
        # Override the OriginAccessControlId property of the CloudFront distribution since it's not supported by CDK
        # https://github.com/aws/aws-cdk/issues/21771#issuecomment-1281190832
        cfn_distribution: cf.CfnDistribution = cdn.node.default_child
        cfn_distribution.add_property_override("DistributionConfig.Origins.0.OriginAccessControlId", oac.attr_id)

        # Allow the CloudFront distribution to invoke the Lambda function (using the Origin Access Control)
        lambda_fn.add_permission(
            "AllowCloudFront",
            action="lambda:InvokeFunctionUrl",
            principal=iam.ServicePrincipal("cloudfront.amazonaws.com"),
            source_arn=f"arn:aws:cloudfront::{self.account}:distribution/{cdn.distribution_id}",
        )

        # Set up Route 53 alias record for the CloudFront distribution
        r53.ARecord(
            self,
            "AliasRecord",
            zone=zone,
            target=r53.RecordTarget.from_alias(r53_targets.CloudFrontTarget(cdn)),
            record_name=host_name,
        )
        # Output the CloudFront distribution URL
        core.CfnOutput(self, "GradioUrl", value=f"https://{fqdn}")
