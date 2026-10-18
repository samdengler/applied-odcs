#!/usr/bin/env node
// One stack in the personal account, us-east-1, default profile.  With no
// variant this is AppliedOdcs, unchanged; -c variant=runtime synthesizes
// AppliedOdcsRuntime, the port to an MCP server on AgentCore Runtime.
import * as cdk from 'aws-cdk-lib';
import { GovernedToolStack, Variant } from '../lib/governed-tool-stack';

const app = new cdk.App();
const variant = (app.node.tryGetContext('variant') || '') as string;
if (variant !== '' && variant !== 'runtime') {
  throw new Error(`unknown variant ${JSON.stringify(variant)}: use no variant or variant=runtime`);
}
const STACKS: Record<Variant, { id: string; description: string }> = {
  '': {
    id: 'AppliedOdcs',
    description: 'applied-odcs: one governed MCP tool behind an AgentCore Gateway with cedar-odcs interceptors',
  },
  runtime: {
    id: 'AppliedOdcsRuntime',
    description: 'applied-odcs runtime: the governed MCP tool on AgentCore Runtime behind an AgentCore Gateway with cedar-odcs interceptors',
  },
};
new GovernedToolStack(app, STACKS[variant as Variant].id, {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: 'us-east-1' },
  description: STACKS[variant as Variant].description,
  variant: variant as Variant,
});
