#!/usr/bin/env node
import * as cdk from 'aws-cdk-lib';
import { CicdPipelineStack } from '../lib/stacks/cicd-pipeline-stack';
import { IngestionPipelineStack } from '../lib/stacks/ingestion-pipeline-stack';

const app = new cdk.App();

const env = {
  account: '022074716478',
  region: 'eu-west-2',
};

// 1. Direct Stack for local diffing & developer validation
new IngestionPipelineStack(app, 'WithingsIngestionPipelineStack', { env });

// 2. Self-Mutating CI/CD Pipeline
const connectionArn =
  process.env.GITHUB_CONNECTION_ARN ||
  'arn:aws:codeconnections:eu-west-2:022074716478:connection/9936e281-8295-4c57-8509-ef059fee208a';

new CicdPipelineStack(app, 'WithingsCicdPipelineStack', {
  env,
  connectionArn,
});
