"""Prints the field names the directory tool last returned, from its log.

The tool logs names and never values.  CloudWatch takes a few seconds to
show a line, so this waits up to 30 seconds for one from the last minute.
"""

import json
import os
import time

import boto3


def main() -> None:
    logs = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    start = int((time.time() - 60) * 1000)
    deadline = time.time() + 30
    pages = logs.get_paginator("filter_log_events")
    while True:
        messages = [event["message"] for page in pages.paginate(
            logGroupName=os.environ["DIRECTORY_TOOL_LOG_GROUP"], startTime=start, filterPattern='"returned "')
            for event in page["events"]]
        if messages:
            print("the tool returned:", ", ".join(json.loads(messages[-1].split("returned ", 1)[1])))
            return
        if time.time() >= deadline:
            print("no tool log line in the last minute")
            return
        time.sleep(3)


if __name__ == "__main__":
    main()
