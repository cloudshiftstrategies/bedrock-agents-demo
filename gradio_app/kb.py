import os
from textwrap import dedent
from gradio_app.helpers import Boto
import pandas as pd

BOTO = Boto()


def get_kb_ingestion_jobs(max_results=25) -> pd.DataFrame:
    """Returns a DataFrame of the ingestion jobs for the knowledge base"""
    datasource_id = os.environ.get("DATASOURCE_ID")
    kb_id = os.environ.get("KB_ID")
    paginator = BOTO.bedrock_client.get_paginator("list_ingestion_jobs")
    response_iterator = paginator.paginate(dataSourceId=datasource_id, knowledgeBaseId=kb_id, maxResults=max_results)
    all_jobs = []
    for page in response_iterator:
        all_jobs.extend(page.get("ingestionJobSummaries", []))
    df = pd.DataFrame(all_jobs)
    if df.empty:
        return df
    df = pd.concat([df.drop(["statistics"], axis=1), df["statistics"].apply(pd.Series)], axis=1)  # Flatten stats
    df["updatedAt"] = pd.to_datetime(df["updatedAt"], utc=True).dt.tz_convert("US/Central")  # Convert to CST
    df["startedAt"] = pd.to_datetime(df["startedAt"], utc=True).dt.tz_convert("US/Central")  # Convert to CST
    df["startedAt"] = df["startedAt"].dt.strftime("%Y-%m-%d %H:%M:%S")  # Format the date
    df["updatedAt"] = df["updatedAt"].dt.strftime("%Y-%m-%d %H:%M:%S")  # Format the date
    df.drop(columns=["dataSourceId", "knowledgeBaseId"], inplace=True)  # Drop these columns
    df = df[["ingestionJobId"] + [col for col in df.columns if col != "ingestionJobId"]]  # Move jobId to the front
    df.sort_values(by="updatedAt", ascending=False, inplace=True)  # Sort by updatedAt
    return df


def get_kb_docs() -> str:
    bucket_name = os.environ.get("KB_BUCKET")
    response = BOTO.s3_client.list_objects_v2(Bucket=bucket_name)
    # Extract the relevant details
    files = []
    for content in response.get("Contents") or []:
        file_key = content["Key"]
        get_url = BOTO.s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket_name, "Key": file_key}, ExpiresIn=3600  # URL valid for 1 hour
        )
        delete_url = BOTO.s3_client.generate_presigned_url(
            "delete_object", Params={"Bucket": bucket_name, "Key": file_key}, ExpiresIn=3600  # URL valid for 1 hour
        )
        delete_html = dedent(
            f"""<button style='background-color: #f44336;'
                onclick=\"fetch('{delete_url}', {{method: 'DELETE'}}).then(() => location.reload())\">Delete</button>"""
        )
        files.append(
            {
                "Article": f'<a href="{get_url}" target="_blank">{file_key}</a>',
                "LastModified": content["LastModified"],
                "Size (MB)": round(float(content["Size"]) / 1024, 1),
                "Delete": delete_html,
            }
        )

    # Convert to DataFrame for a table representation
    df = pd.DataFrame(files)
    return df.to_html(escape=False)  # Return the HTML representation of the DataFrame


def upload_kb_doc(file_path):
    BOTO.s3_client.upload_file(file_path, os.environ.get("KB_BUCKET"), os.path.basename(file_path))
    return get_kb_docs()
