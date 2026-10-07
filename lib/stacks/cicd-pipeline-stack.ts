// lib/stacks/cicd-pipeline-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as pipelines from 'aws-cdk-lib/pipelines';
import * as codebuild from 'aws-cdk-lib/aws-codebuild';
import { Construct } from 'constructs';
import { TelemetryPipelineAppStage } from '../stages/pipeline-stage';

interface CicdPipelineStackProps extends cdk.StackProps {
  connectionArn: string;
}

export class CicdPipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: CicdPipelineStackProps) {
    super(scope, id, props);

    const pipeline = new pipelines.CodePipeline(this, 'Pipeline', {
      pipelineName: 'WithingsTelemetry-CicdPipeline',
      selfMutation: true,
      synth: new pipelines.ShellStep('Synth', {
        input: pipelines.CodePipelineSource.connection(
          'ideaclara/withings-data-on-aws',
          'main',
          {
            connectionArn: props.connectionArn,
          }
        ),
        commands: [
          'node -v',
          'npm ci || npm install',
          'npx cdk synth',
        ],
      }),
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxBuildImage.STANDARD_7_0, // Standard 7.0 supports Node 18, 20, 22
          environmentVariables: {
            NODE_VERSION: { value: '22' },
          },
        },
      },
    });

    // Deploy to London (eu-west-2)
    const prodStage = new TelemetryPipelineAppStage(this, 'Prod', {
      env: {
        account: process.env.CDK_DEFAULT_ACCOUNT,
        region: 'eu-west-2',
      },
    });

    pipeline.addStage(prodStage);
  }
}