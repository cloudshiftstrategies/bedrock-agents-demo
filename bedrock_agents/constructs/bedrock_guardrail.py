import aws_cdk as core
from typing import List
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_kms as kms
from constructs import Construct


class BedrockGuardrail(Construct):
    def __init__(
        self,
        scope: Construct,
        id: str,
        name: str,
        description: str = None,
        blocked_input_messaging: str = None,
        blocked_outputs_messaging: str = None,
        content_policy_config: bedrock.CfnGuardrail.ContentPolicyConfigProperty = None,
        sensitive_information_policy_config: bedrock.CfnGuardrail.SensitiveInformationPolicyConfigProperty = None,
        topic_policy_config: bedrock.CfnGuardrail.TopicPolicyConfigProperty = None,
        word_policy_config: bedrock.CfnGuardrail.WordPolicyConfigProperty = None,
        kms_key: kms.IKey = None,
        tags: List[core.CfnTag] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        self.guardrail = bedrock.CfnGuardrail(
            self,
            "Guardrail",
            name=name,
            description=description,
            blocked_input_messaging=blocked_input_messaging or f"Input BLOCKED by Guardrail: {name}",
            blocked_outputs_messaging=blocked_outputs_messaging or f"Output BLOCKED by Guardrail: {name}",
            content_policy_config=content_policy_config,
            sensitive_information_policy_config=sensitive_information_policy_config,
            topic_policy_config=topic_policy_config,
            word_policy_config=word_policy_config,
            tags=tags,
            kms_key_arn=kms_key.key_arn if kms_key else None,
        )

        self.version = bedrock.CfnGuardrailVersion(
            self,
            "GuardrailVersion",
            guardrail_identifier=self.guardrail.attr_guardrail_id,
        )

    @property
    def agent_configuration(self):
        return bedrock.CfnAgent.GuardrailConfigurationProperty(
            guardrail_identifier=self.guardrail.attr_guardrail_id,
            guardrail_version=self.version.attr_version,
        )
