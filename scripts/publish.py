"""Publishes a use case folder's policy file: the registry's part, stood in for.

Writes build/policies/<target>.json from the folder (after cedar-odcs
build), and with --upload puts it in POLICY_BUCKET as <target>.json.
The deployed interceptors read it within CEDAR_ODCS_POLICIES_TTL
seconds; nothing is redeployed.

    uv run python scripts/publish.py hr
    uv run --env-file .env.applied-odcs-shared python scripts/publish.py hr --upload
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from interceptor.policy_file import from_folder  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()

    document = from_folder(ROOT / args.folder)
    text = json.dumps(document, indent=2) + "\n"
    target = document["target"]
    out = ROOT / "build" / "policies" / f"{target}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    print(f"wrote {out.relative_to(ROOT)}: {len(document['tools'])} tools, "
          f"{len(document['entities'])} entities, {document['policies'].count('@id(')} policies")
    if args.upload:
        import boto3

        bucket = os.environ["POLICY_BUCKET"]
        s3 = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        put = s3.put_object(Bucket=bucket, Key=f"{target}.json", Body=text.encode(), ContentType="application/json")
        print(f"published s3://{bucket}/{target}.json, ETag {put['ETag']}, version {put.get('VersionId')}")


if __name__ == "__main__":
    main()
