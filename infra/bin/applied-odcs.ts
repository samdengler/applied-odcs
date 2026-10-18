#!/usr/bin/env node
// One stack in the personal account, us-east-1, default profile.
import * as cdk from 'aws-cdk-lib';
import { GovernedToolStack } from '../lib/governed-tool-stack';

const app = new cdk.App();
new GovernedToolStack(app, 'AppliedOdcs', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'us-east-1' },
  description: 'applied-odcs: one governed MCP tool behind an AgentCore Gateway with cedar-odcs interceptors',
});
