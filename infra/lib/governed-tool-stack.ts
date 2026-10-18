// The governed tool: Cognito standing in for Ping, the orders tool
// Lambda, the two cedar-odcs interceptors, and the Gateway in MCP mode.
// Plain aws-cdk-lib.  Each construct names the Delta construct it maps
// onto, so the port is a class swap and no change to the Python.
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

const REPO = path.join(__dirname, '..', '..');

export class GovernedToolStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Users and Client: Ping replaces both; Client is PingConfiguration.allowedClients.
    const users = new cognito.UserPool(this, 'Users', {
      userPoolName: 'applied-odcs',
      selfSignUpEnabled: false,
      signInAliases: { username: true },
      standardAttributes: { email: { required: true, mutable: true } },
      mfa: cognito.Mfa.OFF,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });
    const client = new cognito.UserPoolClient(this, 'Client', {
      userPool: users,
      generateSecret: false,
      authFlows: { userPassword: true },
      accessTokenValidity: cdk.Duration.hours(1),
    });
    // Roles in the Ping token.
    for (const [id, groupName] of [['SupportGroup', 'support'], ['FinanceGroup', 'finance'], ['EmployeeGroup', 'employee']]) {
      new cognito.CfnUserPoolGroup(this, id, { userPoolId: users.userPoolId, groupName });
    }

    const logGroup = (id: string) => new logs.LogGroup(this, id, {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // The Lambda behind DeltaLambdaGatewayTarget.
    const ordersTool = new lambda.Function(this, 'OrdersTool', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      code: lambda.Code.fromAsset(path.join(REPO, 'orders', 'tool')),
      handler: 'handler.handler',
      memorySize: 256,
      timeout: cdk.Duration.seconds(10),
      logGroup: logGroup('OrdersToolLogs'),
    });

    // The interceptor code either way: built by lambda/bundle.sh, shared by
    // both functions.  CEDAR_ODCS_RECORD logs each inbound event so make
    // record can save it; deploy with -c record=false to turn it off.
    const interceptors = lambda.Code.fromAsset(path.join(REPO, 'build', 'lambda'));
    const record = this.node.tryGetContext('record') !== 'false';
    const interceptor = (id: string, handler: string) => new lambda.Function(this, id, {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      code: interceptors,
      handler,
      memorySize: 512,
      timeout: cdk.Duration.seconds(10),
      environment: {
        CEDAR_ODCS_USE_CASE: '/var/task/orders',
        ...(record ? { CEDAR_ODCS_RECORD: '1' } : {}),
      },
      logGroup: logGroup(`${id}Logs`),
    });
    // requestInterceptor.interceptorFunction and responseInterceptor.interceptorFunction
    // (the Delta construct adds the kill switch layer).
    const requestInterceptor = interceptor('RequestInterceptor', 'cedar_odcs.gateway.handler.request');
    const responseInterceptor = interceptor('ResponseInterceptor', 'cedar_odcs.gateway.handler.response');

    // DeltaAgentCoreGateway.
    const gateway = new agentcore.Gateway(this, 'Gateway', {
      gatewayName: 'applied-odcs',
      protocolConfiguration: new agentcore.McpProtocolConfiguration({
        instructions: 'Orders tools.  Every call is decided by cedar-odcs from the orders ODCS contract and Cedar policies.',
        supportedVersions: [agentcore.MCPProtocolVersion.MCP_2025_06_18, agentcore.MCPProtocolVersion.MCP_2025_03_26],
      }),
      authorizerConfiguration: agentcore.GatewayAuthorizer.usingCognito({ userPool: users, allowedClients: [client] }),
      exceptionLevel: agentcore.GatewayExceptionLevel.DEBUG,
      interceptorConfigurations: [
        agentcore.LambdaInterceptor.forRequest(requestInterceptor, { passRequestHeaders: true }),
        agentcore.LambdaInterceptor.forResponse(responseInterceptor, { passRequestHeaders: true }),
      ],
    });

    // DeltaLambdaGatewayTarget.  The Gateway names each tool orders___<tool>.
    gateway.addLambdaTarget('Orders', {
      gatewayTargetName: 'orders',
      lambdaFunction: ordersTool,
      toolSchema: agentcore.ToolSchema.fromLocalAsset(path.join(REPO, 'orders', 'tools.json')),
    });

    // SSM parameters in the Delta construct.
    new cdk.CfnOutput(this, 'GatewayUrl', { value: gateway.gatewayUrl ?? '' });
    new cdk.CfnOutput(this, 'GatewayId', { value: gateway.gatewayId });
    new cdk.CfnOutput(this, 'UserPoolId', { value: users.userPoolId });
    new cdk.CfnOutput(this, 'ClientId', { value: client.userPoolClientId });
    new cdk.CfnOutput(this, 'Region', { value: this.region });
    new cdk.CfnOutput(this, 'RequestLogGroup', { value: requestInterceptor.logGroup.logGroupName });
    new cdk.CfnOutput(this, 'ResponseLogGroup', { value: responseInterceptor.logGroup.logGroupName });
    new cdk.CfnOutput(this, 'ToolLogGroup', { value: ordersTool.logGroup.logGroupName });
  }
}
