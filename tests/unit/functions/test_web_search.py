from unittest import mock
import json
from bedrock_agents.functions import web_search
import pytest
from tests.unit.mock_data import bedrock_event


@mock.patch("requests.get")
@mock.patch.dict(bedrock_event)
def test_lambda_handler_retrieve(mock_get):
    url = "https://foo.com"
    bedrock_event["function"] = "retrieve"
    bedrock_event["parameters"] = [{"name": "url", "type": "string", "value": url}]
    mock_get.return_value.status_code = 200
    data = {"url": url, "content": "sample respyyonse"}
    mock_get.return_value.text = json.dumps({"data": data})

    result = web_search.lambda_handler(bedrock_event, mock.MagicMock())
    response = web_search.BedrockResponseEvent.model_validate(result)
    assert response.response.functionResponse.responseBody["TEXT"].body == json.dumps(data)
    assert mock_get.called_with("https://r.jina.ai/https://foo.com")
    assert "Authorization" in mock_get.call_args.kwargs["headers"]
    assert "Bearer jina_" in mock_get.call_args.kwargs["headers"]["Authorization"]


@mock.patch("requests.get")
@mock.patch.dict(bedrock_event)
def test_lambda_handler_search(mock_get):
    bedrock_event["function"] = "search"
    search_str = "search string"
    bedrock_event["parameters"] = [{"name": "query", "type": "string", "value": search_str}]
    mock_get.return_value.status_code = 200
    data = [{"url": "https://foo.com", "content": "sample respyyonse"}]
    mock_get.return_value.text = json.dumps({"data": data})

    result = web_search.lambda_handler(bedrock_event, mock.MagicMock())
    response = web_search.BedrockResponseEvent.model_validate(result)
    assert response.response.functionResponse.responseBody["TEXT"].body == json.dumps(data)
    assert mock_get.called_with("https://r.jina.ai/When was cloudshift founded")


@mock.patch("requests.get")
@mock.patch.dict(bedrock_event)
def test_lambda_handler_invalid_function(mock_get):
    bedrock_event["function"] = "invalid"
    result = web_search.lambda_handler(bedrock_event, mock.MagicMock())
    response = web_search.BedrockResponseEvent.model_validate(result)
    assert response.response.functionResponse.responseState == "FAILURE"
    assert response.response.functionResponse.responseBody["TEXT"].body == "Invalid function: invalid"


if __name__ == "__main__":
    pytest.main()
