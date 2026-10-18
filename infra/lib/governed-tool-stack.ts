// The governed tool: Cognito standing in for Ping, the orders tool
// Lambda, the two cedar-odcs interceptors, and the Gateway in MCP mode.
// Plain aws-cdk-lib.  Each construct names the Delta construct it maps
// onto, so the port is a class swap and no change to the Python.
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import { Construct } from 'constructs';

const REPO = path.join(__dirname, '..', '..');

// '' is AppliedOdcs with a Lambda function target; 'runtime' is
// AppliedOdcsRuntime, every physical name prefixed applied-odcs-runtime.
export type Variant = '' | 'runtime';

export interface GovernedToolStackProps extends cdk.StackProps {
  readonly variant?: Variant;
}

export class GovernedToolStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: GovernedToolStackProps = {}) {
    super(scope, id, props);
    const variant = props.variant ?? '';
    // Every physical name derives from this.  Log groups and functions are
    // named by CloudFormation.
    const prefix = variant ? `applied-odcs-${variant}` : 'applied-odcs';

    // Users and Client: Ping replaces both; Client is PingConfiguration.allowedClients.
    const users = new cognito.UserPool(this, 'Users', {
      userPoolName: prefix,
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

    // The Lambda behind DeltaLambdaGatewayTarget, in the default variant only.
    const ordersTool = variant ? undefined : new lambda.Function(this, 'OrdersTool', {
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
      gatewayName: prefix,
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
    if (ordersTool) {
      gateway.addLambdaTarget('Orders', {
        gatewayTargetName: 'orders',
        lambdaFunction: ordersTool,
        toolSchema: agentcore.ToolSchema.fromLocalAsset(path.join(REPO, 'orders', 'tools.json')),
      });
    }
    const runtime = variant === 'runtime' ? this.ordersRuntime(prefix, users, gateway) : undefined;

    // SSM parameters in the Delta construct.
    new cdk.CfnOutput(this, 'GatewayUrl', { value: gateway.gatewayUrl ?? '' });
    new cdk.CfnOutput(this, 'GatewayId', { value: gateway.gatewayId });
    new cdk.CfnOutput(this, 'UserPoolId', { value: users.userPoolId });
    new cdk.CfnOutput(this, 'ClientId', { value: client.userPoolClientId });
    new cdk.CfnOutput(this, 'Region', { value: this.region });
    new cdk.CfnOutput(this, 'RequestLogGroup', { value: requestInterceptor.logGroup.logGroupName });
    new cdk.CfnOutput(this, 'ResponseLogGroup', { value: responseInterceptor.logGroup.logGroupName });
    if (ordersTool) {
      new cdk.CfnOutput(this, 'ToolLogGroup', { value: ordersTool.logGroup.logGroupName });
    }
    if (runtime) {
      new cdk.CfnOutput(this, 'RuntimeArn', { value: runtime.runtime.agentRuntimeArn });
      new cdk.CfnOutput(this, 'RuntimeLogGroup', { value: runtime.runtime.applicationLogGroup.logGroupName });
      new cdk.CfnOutput(this, 'M2MClientId', { value: runtime.m2mClient.userPoolClientId });
      new cdk.CfnOutput(this, 'TokenEndpoint', { value: runtime.tokenEndpoint });
    }
  }

  // The runtime variant: the orders MCP server on AgentCore Runtime, and
  // the Gateway's MCP server target calling it with an OAuth token issued
  // to a Cognito M2M client.  DeltaAgentCoreRuntimeMcp builds the same
  // with a Ping client named by credentialSecretName.
  private ordersRuntime(prefix: string, users: cognito.UserPool, gateway: agentcore.Gateway) {
    // The M2M client's grant: one scope on a resource server, and a domain
    // for the token endpoint.  Ping supplies all three in Delta.
    const invoke = new cognito.ResourceServerScope({ scopeName: 'invoke', scopeDescription: 'Call the orders MCP server' });
    const resourceServer = users.addResourceServer('OrdersResourceServer', {
      identifier: 'orders',
      userPoolResourceServerName: `${prefix}-orders`,
      scopes: [invoke],
    });
    const domain = users.addDomain('Domain', { cognitoDomain: { domainPrefix: `${prefix}-${this.account}` } });
    const m2mClient = users.addClient('M2MClient', {
      generateSecret: true,
      authFlows: {},
      oAuth: {
        flows: { clientCredentials: true },
        scopes: [cognito.OAuthScope.resourceServer(resourceServer, invoke)],
      },
      accessTokenValidity: cdk.Duration.hours(1),
    });
    const tokenEndpoint = `${domain.baseUrl()}/oauth2/token`;

    // DeltaAgentCoreRuntimeMcp: protocol MCP, ARM64, from build/server.
    // Only tokens issued to the M2M client get in.
    const runtime = new agentcore.Runtime(this, 'OrdersRuntime', {
      runtimeName: `${prefix.replace(/-/g, '_')}_orders`,
      description: 'The orders MCP server.  It does no authorization; the Gateway interceptors decide every call.',
      agentRuntimeArtifact: agentcore.AgentRuntimeArtifact.fromAsset(path.join(REPO, 'build', 'server'), {
        platform: ecrAssets.Platform.LINUX_ARM64,
      }),
      protocolConfiguration: agentcore.ProtocolType.MCP,
      // V2 starts sessions faster, and the Gateway opens a new Runtime
      // session for every tool call.  Unset, the service default is V1.
      platformVersion: agentcore.PlatformVersion.V2,
      authorizerConfiguration: agentcore.RuntimeAuthorizerConfiguration.usingCognito(users, [m2mClient]),
    });

    // The Gateway's outbound credential: the Token Vault holds the M2M
    // client's id and secret.  Delta reads them from credentialSecretName.
    const credential = agentcore.OAuth2CredentialProvider.usingCognito(this, 'OrdersOAuth', {
      oAuth2CredentialProviderName: `${prefix}-orders`,
      clientId: m2mClient.userPoolClientId,
      clientSecret: m2mClient.userPoolClientSecret,
      issuer: users.userPoolProviderUrl,
      authorizationEndpoint: `${domain.baseUrl()}/oauth2/authorize`,
      tokenEndpoint,
    });

    // The Runtime's invocation endpoint, the form the Delta constructs use:
    // the ARN URL-encoded, ':' as %3A and '/' as %2F.
    const encodedArn = cdk.Fn.join('%2F', cdk.Fn.split('/', cdk.Fn.join('%3A', cdk.Fn.split(':', runtime.agentRuntimeArn))));
    const target = gateway.addMcpServerTarget('Orders', {
      gatewayTargetName: 'orders',
      endpoint: `https://bedrock-agentcore.${this.region}.amazonaws.com/runtimes/${encodedArn}/invocations?qualifier=DEFAULT`,
      credentialProviderConfigurations: [
        agentcore.GatewayCredentialProvider.fromOauthIdentity(credential, { scopes: [`orders/${invoke.scopeName}`] }),
      ],
    });
    // The L2 leaves the grant type to the service default; the M2M client
    // has only the client credentials grant, so say so.
    (target.node.defaultChild as agentcore.CfnGatewayTarget).addPropertyOverride(
      'CredentialProviderConfigurations.0.CredentialProvider.OauthCredentialProvider.GrantType', 'CLIENT_CREDENTIALS');
    return { runtime, m2mClient, tokenEndpoint };
  }
}
