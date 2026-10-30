// The governed tool: Cognito standing in for Ping, the HR tool Lambda, the
// shared cedar-odcs interceptor, the bucket it reads policy files from, and
// the Gateway in MCP mode.  Plain aws-cdk-lib.  Each construct names the
// Delta construct it maps onto, so the port is a class swap and no change
// to the Python.
import * as path from 'path';
import * as cdk from 'aws-cdk-lib';
import * as agentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as s3 from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

const REPO = path.join(__dirname, '..', '..');
// Every physical name, kept apart from main's AppliedOdcs stack.
const NAME = 'applied-odcs-shared';

export class GovernedToolStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Users and Client: Ping replaces both; Client is PingConfiguration.allowedClients.
    const users = new cognito.UserPool(this, 'Users', {
      userPoolName: NAME,
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
    // No groups: the HR policies read no role, only the caller's username.

    const logGroup = (id: string) => new logs.LogGroup(this, id, {
      retention: logs.RetentionDays.ONE_WEEK,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
    });

    // The Lambda behind DeltaLambdaGatewayTarget: the HR API stand-in.
    const hrTool = new lambda.Function(this, 'HrTool', {
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      code: lambda.Code.fromAsset(path.join(REPO, 'hr', 'tool')),
      handler: 'handler.handler',
      memorySize: 256,
      timeout: cdk.Duration.seconds(10),
      logGroup: logGroup('HrToolLogs'),
    });

    // Where the registry publishes each target's policy file, <target>.json
    // (interceptor/policy_file.py).  In Delta the bucket is the registry's;
    // this stack owns it only for the demo.  Versioned, so a published file
    // can be rolled back.
    const policies = new s3.Bucket(this, 'Policies', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // The interceptor code, the same for every target: built by
    // lambda/bundle.sh, shared by both functions, with no use case in it.
    // CEDAR_ODCS_RECORD logs each inbound event so make record can save it;
    // deploy with -c record=false to turn it off.
    const interceptors = lambda.Code.fromAsset(path.join(REPO, 'build', 'lambda'));
    const record = this.node.tryGetContext('record') !== 'false';
    const interceptor = (id: string, handler: string) => {
      const fn = new lambda.Function(this, id, {
        runtime: lambda.Runtime.PYTHON_3_12,
        architecture: lambda.Architecture.ARM_64,
        code: interceptors,
        handler,
        memorySize: 512,
        timeout: cdk.Duration.seconds(10),
        environment: {
          CEDAR_ODCS_POLICIES: `s3://${policies.bucketName}/`,
          CEDAR_ODCS_POLICIES_TTL: '60',
          // The claims of a Cognito access token; Ping's go here instead.
          CEDAR_ODCS_CLAIMS: JSON.stringify({ subject: 'username', roles: 'cognito:groups' }),
          ...(record ? { CEDAR_ODCS_RECORD: '1' } : {}),
        },
        logGroup: logGroup(`${id}Logs`),
      });
      policies.grantRead(fn);
      return fn;
    };
    // requestInterceptor.interceptorFunction and responseInterceptor.interceptorFunction
    // (the Delta construct adds the kill switch layer).
    const requestInterceptor = interceptor('RequestInterceptor', 'interceptor.handler.request');
    const responseInterceptor = interceptor('ResponseInterceptor', 'interceptor.handler.response');

    // DeltaAgentCoreGateway.
    const gateway = new agentcore.Gateway(this, 'Gateway', {
      gatewayName: NAME,
      protocolConfiguration: new agentcore.McpProtocolConfiguration({
        instructions: 'HR tools.  Every call is decided by cedar-odcs from the policy file published for its target.',
        supportedVersions: [agentcore.MCPProtocolVersion.MCP_2025_06_18, agentcore.MCPProtocolVersion.MCP_2025_03_26],
      }),
      authorizerConfiguration: agentcore.GatewayAuthorizer.usingCognito({ userPool: users, allowedClients: [client] }),
      exceptionLevel: agentcore.GatewayExceptionLevel.DEBUG,
      interceptorConfigurations: [
        agentcore.LambdaInterceptor.forRequest(requestInterceptor, { passRequestHeaders: true }),
        agentcore.LambdaInterceptor.forResponse(responseInterceptor, { passRequestHeaders: true }),
      ],
    });

    // DeltaLambdaGatewayTarget.  The Gateway names each tool hr___<tool>,
    // and the interceptor reads hr.json for it.
    gateway.addLambdaTarget('Hr', {
      gatewayTargetName: 'hr',
      lambdaFunction: hrTool,
      toolSchema: agentcore.ToolSchema.fromLocalAsset(path.join(REPO, 'hr', 'tools.json')),
    });

    // SSM parameters in the Delta construct.
    new cdk.CfnOutput(this, 'GatewayUrl', { value: gateway.gatewayUrl ?? '' });
    new cdk.CfnOutput(this, 'GatewayId', { value: gateway.gatewayId });
    new cdk.CfnOutput(this, 'UserPoolId', { value: users.userPoolId });
    new cdk.CfnOutput(this, 'ClientId', { value: client.userPoolClientId });
    new cdk.CfnOutput(this, 'Region', { value: this.region });
    new cdk.CfnOutput(this, 'PolicyBucket', { value: policies.bucketName });
    new cdk.CfnOutput(this, 'RequestLogGroup', { value: requestInterceptor.logGroup.logGroupName });
    new cdk.CfnOutput(this, 'ResponseLogGroup', { value: responseInterceptor.logGroup.logGroupName });
    new cdk.CfnOutput(this, 'ToolLogGroup', { value: hrTool.logGroup.logGroupName });
  }
}
