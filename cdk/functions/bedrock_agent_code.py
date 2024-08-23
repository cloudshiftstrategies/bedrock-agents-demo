#!/usr/bin/env python
import json
import time
from typing import Optional, List
import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.logging.formatter import LambdaPowertoolsFormatter
from aws_lambda_powertools.utilities.data_classes import event_source, CloudFormationCustomResourceEvent
from datetime import datetime

formatter = LambdaPowertoolsFormatter(utc=True, log_record_order=["message", "params"])
logger = Logger(service="bedrock-code", logger_formatter=formatter)
logger.setLevel("INFO")

DEFAULT_REGION = "us-east-1"
AGENT_GROUP_NAME = "code_interpreter"
TEMP_ALIAS_NAME = f"CFN-TEMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"


class Agent:
    """Class to manage Bedrock Agent"""

    agent_id: str
    _client: boto3.client
    _prepared_agent_details: dict

    def __init__(self, agent_id):
        self.agent_id = agent_id
        self._client = None
        self._prepared_agent_details = None

    @property
    def client(self) -> boto3.client:
        """Return a boto3 client for bedrock-agent"""
        if not self._client:
            self._client = boto3.client("bedrock-agent")
        return self._client

    @property
    def prepared_agent_details(self) -> dict:
        """Return the details of the last boto prepare_agent() invocation"""
        if not self._prepared_agent_details:
            self._prepared_agent_details = self._prepare_agent()
        return self._prepared_agent_details

    @property
    def agent_prepared_version(self) -> str:
        """Return the version of the agent that was prepared"""
        return str(self.prepared_agent_details["agentVersion"])

    def _get_agent(self) -> dict:
        """Return the agent details using boto get_agent()"""
        return self.client.get_agent(agentId=self.agent_id)["agent"]

    def _get_agent_action_groups(self) -> List[dict]:
        """Return the agent action groups using boto list_agent_action_groups()"""
        return self.client.list_agent_action_groups(
            agentId=self.agent_id, agentVersion=self.prepared_agent_details["agentVersion"]
        )["actionGroupSummaries"]

    def _get_agent_knowledge_bases(self) -> List[dict]:
        """Return the agent knowledge bases using boto list_agent_knowledge_bases()"""
        knowledge_bases = []

        paginator = self.client.get_paginator("list_agent_knowledge_bases")
        for page in paginator.paginate(
            agentId=self.agent_id,
            agentVersion=self.agent_prepared_version,
            PaginationConfig={"PageSize": 10},
        ):
            knowledge_bases.extend(page["agentKnowledgeBaseSummaries"])
        return knowledge_bases

    def _get_alias_id(self, agent_alias_name: str) -> Optional[str]:
        """Return the agent alias id using boto list_agent_aliases()"""
        paginator = self.client.get_paginator("list_agent_aliases")
        for page in paginator.paginate(agentId=self.agent_id):
            for alias in page["agentAliasSummaries"]:
                if alias["agentAliasName"] == agent_alias_name:
                    return alias["agentAliasId"]

    def _wait_for_agent_status(self, status) -> None:
        """Wait for the agent status to be the desired status"""
        while self.client.get_agent(agentId=self.agent_id)["agent"]["agentStatus"] != status:
            time.sleep(2)

    def _wait_for_alias_status(self, agent_alias_name: str, status) -> None:
        """Wait for the agent alias status to be the desired status"""
        agent_alias_id = self._get_alias_id(agent_alias_name)
        while (
            self.client.get_agent_alias(agentId=self.agent_id, agentAliasId=agent_alias_id)["agentAlias"][
                "agentAliasStatus"
            ]
            != status
        ):
            time.sleep(2)

    def _prepare_agent(self) -> dict:
        """Creates a DRAFT version of the agent, returns the details of the prepared agent"""
        logger.info("prepare_agent() with agent_id", agent_id=self.agent_id)

        prepared_agent_details = self.client.prepare_agent(agentId=self.agent_id)
        self._wait_for_agent_status("PREPARED")

        return prepared_agent_details

    def _create_agent_alias(self, agent_alias_name: str) -> dict:
        """Create an agent alias and wait for it to be prepared"""
        agent_alias = self.client.create_agent_alias(agentId=self.agent_id, agentAliasName=agent_alias_name)
        self._wait_for_agent_status("PREPARED")
        self._wait_for_alias_status(agent_alias_name, "PREPARED")
        return agent_alias

    def _update_agent_alias(self, agent_alias_name: str, agent_version: int) -> dict:
        """Update the agent alias with a new agent version returning the updated agent alias result"""
        agent_alias = self.client.update_agent_alias(
            agentAliasId=self._get_alias_id(agent_alias_name),
            agentAliasName=agent_alias_name,
            agentId=self.agent_id,
            routingConfiguration=[{"agentVersion": agent_version}],
        )
        self._wait_for_agent_status("PREPARED")
        return agent_alias

    def _delete_agent_alias(self, agent_alias_name: str) -> None:
        """Delete the agent alias"""
        agent_alias_id = self._get_alias_id(agent_alias_name)
        self.client.delete_agent_alias(agentId=self.agent_id, agentAliasId=agent_alias_id)

    def _get_agent_alias_version_number(self, agent_alias_name: str) -> Optional[str]:
        """Return the agent version number of the agent alias"""
        result = self.client.get_agent_alias(agentId=self.agent_id, agentAliasId=self._get_alias_id(agent_alias_name))
        return str(result["agentAlias"]["routingConfiguration"][0]["agentVersion"])

    def _get_action_group_id(self, action_group_name: str) -> Optional[str]:
        """Return the action group id if it exists"""
        logger.info("list_agent_action_groups()", agent_id=self.agent_id, agent_version=self.agent_prepared_version)
        result = self.client.list_agent_action_groups(agentId=self.agent_id, agentVersion=self.agent_prepared_version)[
            "actionGroupSummaries"
        ]
        for action_group in result:
            if action_group["actionGroupName"] == action_group_name:
                logger.info(f"code_action_group exists id: {action_group.get('actionGroupId')}")
                return action_group.get("actionGroupId")
        logger.info(
            f"code_action_group named: '{action_group_name}' not found in agent:{self.agent_id} "
            f"v:{self.agent_prepared_version}"
        )

    def _prepare_if_needed(self) -> None:
        """If the agent has been modified or any components have been added, prepare the agent again"""
        components = [self._get_agent()]
        components += self._get_agent_action_groups()
        components += self._get_agent_knowledge_bases()

        latest_update = max(component["updatedAt"] for component in components)
        if latest_update > self.prepared_agent_details["preparedAt"]:
            self._prepared_agent_details = self._prepare_agent()

    def _update_alias_with_new_version(self, agent_alias_name: str) -> None:
        """Update the agent alias with a new version of the currently prepaired agent"""
        if self._get_alias_id(TEMP_ALIAS_NAME):
            self._delete_agent_alias(TEMP_ALIAS_NAME)
        self.agent_alias = self._create_agent_alias(TEMP_ALIAS_NAME)  # This creates a version
        new_agent_version = self._get_agent_alias_version_number(TEMP_ALIAS_NAME)
        self.agent_alias = self._update_agent_alias(agent_alias_name, new_agent_version)
        self._delete_agent_alias(TEMP_ALIAS_NAME)

    def create_agent_code_action_group(self, agent_alias_name: str) -> str:
        """Create or Update the agent code interpreter action group"""
        params = {
            "agentId": self.agent_id,
            "agentVersion": self.agent_prepared_version,
            "actionGroupName": AGENT_GROUP_NAME,
            "parentActionGroupSignature": "AMAZON.CodeInterpreter",
            "actionGroupState": "ENABLED",
        }
        logger.info("create_agent_action_group()", params=params)
        if action_group_id := self._get_action_group_id(AGENT_GROUP_NAME):
            self.client.update_agent_action_group(actionGroupId=action_group_id, **params)
        else:
            self.client.create_agent_action_group(**params)
        self._prepare_if_needed()
        self._update_alias_with_new_version(agent_alias_name)
        return self._get_action_group_id(AGENT_GROUP_NAME)

    def delete_code_action_group(self, agent_alias_name: str) -> None:
        """Delete the agent code interpreter action group"""
        if action_group_id := self._get_action_group_id(AGENT_GROUP_NAME):
            params = {
                "actionGroupId": action_group_id,
                "actionGroupName": AGENT_GROUP_NAME,
                "agentId": self.agent_id,
                "agentVersion": self.agent_prepared_version,
                "parentActionGroupSignature": "AMAZON.CodeInterpreter",
                "actionGroupState": "DISABLED",
            }
            logger.info("update_agent_action_group() with params", params=params)
            self.client.update_agent_action_group(**params)
            logger.info(f"delete_code_action_group() with agent_id:{self.agent_id}")
            params = {
                "actionGroupId": action_group_id,
                "agentId": self.agent_id,
                "agentVersion": self.agent_prepared_version,
            }
            logger.info("delete_agent_action_group() with params", params=params)
            self.client.delete_agent_action_group(**params)
        self._prepare_if_needed()
        self._update_alias_with_new_version(agent_alias_name)


@logger.inject_lambda_context(log_event=True)
@event_source(data_class=CloudFormationCustomResourceEvent)
def lambda_handler(event: CloudFormationCustomResourceEvent, context):

    agent_id = event.resource_properties["agent_id"]
    agent_alias_name = event.resource_properties["agent_alias_name"]
    agent = Agent(agent_id)
    if event.request_type == "Delete":
        agent.delete_code_action_group(agent_alias_name)
        return {}
    elif event.request_type == "Create" or event.request_type == "Update":
        action_group_id = agent.create_agent_code_action_group(agent_alias_name)
        return {"PhysicalResourceId": action_group_id}


if __name__ == "__main__":
    import argparse
    from unittest.mock import MagicMock
    from dotenv import load_dotenv

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Managed Bedrock Agent Code Interpreter Action Group",
    )
    parser.add_argument(
        "action", choices=["create", "delete", "update"], help="Specify the action to perform: create, delete, update"
    )
    parser.add_argument("-i", "--agent_id", help="Agent Id")
    parser.add_argument("-a", "--agent_alias_name", help="Agent Alias Name")

    args = parser.parse_args()
    event = {
        "RequestType": args.action.capitalize(),
        "ResourceProperties": dict(agent_id=args.agent_id, agent_alias_name=args.agent_alias_name),
    }

    result = lambda_handler(event, MagicMock())
    print(json.dumps(result, indent=2))
