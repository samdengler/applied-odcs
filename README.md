# applied-odcs

One governed MCP tool, deployed.  `orders/` is an orders API behind an
Amazon Bedrock AgentCore Gateway, and cedar-odcs's request and response
interceptors decide every call from an ODCS contract and Cedar policies.
Alice, Carol, and Dave are Cognito users; the same `list_orders` call
returns each of them only the rows and fields the contract allows.  The
folder passes `cedar-odcs check` locally with no AWS, and the Gateway
events recorded from live calls are saved as test fixtures.

The plan is `docs/plan.md`; the Makefile is the interface.
