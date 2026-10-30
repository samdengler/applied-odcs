#!/usr/bin/env node
// One stack in the personal account, us-east-1, default profile:
// AppliedOdcsShared.  The earlier orders demo's AppliedOdcs stack, at tag
// demo-lambda-target, is never deployed from here.
import * as cdk from 'aws-cdk-lib';
import { GovernedToolStack } from '../lib/governed-tool-stack';

const app = new cdk.App();
new GovernedToolStack(app, 'AppliedOdcsShared', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'us-east-1' },
  description: 'applied-odcs shared-interceptor: one governed MCP tool behind an AgentCore Gateway, decided by a shared cedar-odcs interceptor from a policy file in S3',
});
