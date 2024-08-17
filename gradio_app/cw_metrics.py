import io
from typing import List, Tuple, Set
import boto3
from datetime import datetime, timedelta, UTC
import pandas as pd
import plotly.express as px


def get_metrics(client: boto3.client) -> Tuple[Set[str], Set[str]]:
    # Get the metrics for Bedrock
    namespace = "AWS/Bedrock"
    all_metrics = client.list_metrics(Namespace=namespace).get("Metrics")
    metric_names = set(map(lambda m: m.get("MetricName"), all_metrics))
    dimensions = list(map(lambda m: m.get("Dimensions"), all_metrics))
    model_ids = set(map(lambda d: d[0].get("Value") if d else None, dimensions))
    model_ids.remove(None)
    return metric_names, model_ids


def get_plots(client: boto3.client, hours=24, period=300):
    metric_names, model_ids = get_metrics(client)
    namespace = 'AWS/Bedrock'
    start_time = datetime.now(UTC) - timedelta(hours=hours)
    end_time = datetime.now(UTC)
    plots: List[px.line] = []
    # plt.Figure = plt.figure(figsize=(10, 6))
    # plt.tight_layout()
    # Loop through all ModelIds and retrieve their metrics
    for metric_name in metric_names:
        metrics_df = pd.DataFrame()
        for model_id in model_ids:
            model_name_id = model_id.replace("-", "_").replace(":", "").replace(".", "_").replace("/", "_")
            start_time = datetime.utcnow() - timedelta(days=1)
            response = client.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": f"m1_{model_name_id}",
                        "MetricStat": {
                            "Metric": {
                                "Namespace": namespace,
                                "MetricName": metric_name,
                                "Dimensions": [
                                    {"Name": "ModelId", "Value": model_id},
                                ],
                            },
                            "Period": period,
                            "Stat": "Average",
                        },
                        "ReturnData": True,
                    },
                ],
                StartTime=start_time,
                EndTime=end_time,
            )
            timestamps = response["MetricDataResults"][0]["Timestamps"]
            values = response["MetricDataResults"][0]["Values"]
            df = pd.DataFrame(
                {
                    "Timestamp": timestamps,
                    "ModelId": model_id,
                    "Metric": metric_name,
                    "Value": values,
                }
            )
            metrics_df = metrics_df.dropna(axis=1, how='all')
            df = df.dropna(axis=1, how='all')
            metrics_df = pd.concat([metrics_df, df])
        metrics_df["ModelId"] = metrics_df["ModelId"].apply(lambda x: x.split("/")[-1])  # Remove the arn prefix
        pivot_df = metrics_df.pivot(index=["Timestamp"], columns="ModelId", values="Value")
        fig = px.line(pivot_df, title=f"Avg {metric_name}, last {hours}hrs, {period} secs")
        plots.append(fig)
    return plots
