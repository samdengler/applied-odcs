# The orders MCP server for AgentCore Runtime: ARM64, port 8000, /mcp.
# Built from build/server by make server-build.  The base image comes
# from ECR Public, not Docker Hub, to avoid its pull limits.
FROM --platform=linux/arm64 public.ecr.aws/docker/library/python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py orders.json ./
EXPOSE 8000
CMD ["python", "server.py"]
