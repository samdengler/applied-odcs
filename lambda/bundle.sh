#!/bin/sh
# Builds build/lambda, the code both interceptor Lambdas run, the same for
# every governed target: interceptor/ and cedar_odcs with its dependencies
# as Linux arm64 wheels for Python 3.12.  No use case is in it; the
# interceptors read each target's policy file from S3.  No Docker.  The
# cedar-odcs pin is the one in pyproject.toml; CEDAR_ODCS_SOURCE overrides it
# (a local checkout path, while iterating on a fix before it is tagged).
set -e
cd "$(dirname "$0")/.."
PIN=${CEDAR_ODCS_SOURCE:-$(grep -o '"cedar-odcs @ [^"]*"' pyproject.toml | tr -d '"')}

rm -rf build/lambda && mkdir -p build/lambda
uv pip install --quiet --target build/lambda \
  --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --only-binary :all: \
  "$PIN"
rsync -a --exclude 'test_*' --exclude __pycache__ interceptor/ build/lambda/interceptor/
ls -d build/lambda/cedarpy* build/lambda/cedar_odcs build/lambda/interceptor/handler.py
