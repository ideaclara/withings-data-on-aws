#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CicdPipelineStack } from '../lib/stacks/cicd-pipeline-stack';
import { IngestionPipelineStack } from '../lib/stacks/ingestion-pipeline-stack';

const app = new cdk.App();

const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT || '022074716478',
  region: 'eu-west-2',
};

// 1. Direct Stack (for rapid local developer iteration & direct diffing)
new IngestionPipelineStack(app, 'WithingsIngestionPipelineStack', { env });

// 2. CI/CD Self-Mutating Pipeline
const connectionArn =
  process.env.GITHUB_CONNECTION_ARN ||
  'arn:aws:codeconnections:eu-west-2:022074716478:connection/9936e281-8295-4c57-8509-ef059fee208a';

new CicdPipelineStack(app, 'WithingsCicdPipelineStack', {
  env,
  connectionArn,
});
