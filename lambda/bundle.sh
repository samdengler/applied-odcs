#!/bin/sh
# Builds build/lambda, the code both interceptor Lambdas run: cedar_odcs
# and its dependencies as Linux arm64 wheels for Python 3.12, plus orders/
# with the files the build generates from the contract.  No Docker.  The
# cedar-odcs pin is the one in pyproject.toml.
set -e
cd "$(dirname "$0")/.."
PIN=$(grep -o '"cedar-odcs @ [^"]*"' pyproject.toml | tr -d '"')

rm -rf build/lambda && mkdir -p build/lambda
uv pip install --quiet --target build/lambda \
  --python-platform aarch64-manylinux2014 --python-version 3.12 \
  --only-binary :all: \
  "$PIN"
uv run cedar-odcs build orders
rsync -a --exclude tests --exclude tool --exclude contract/unity --exclude __pycache__ \
  orders/ build/lambda/orders/
ls -d build/lambda/cedarpy* build/lambda/cedar_odcs build/lambda/orders/entities.json
