import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { IngestionPipelineStack } from '../stacks/ingestion-pipeline-stack';

export class TelemetryPipelineAppStage extends cdk.Stage {
  constructor(scope: Construct, id: string, props?: cdk.StageProps) {
    super(scope, id, props);

    new IngestionPipelineStack(this, 'WithingsIngestionPipelineStack');
  }
}
