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
        installCommands: [
          'nvm use 20 || nvm install 20',
          'node -v',
          'npm install',
        ],
        commands: [
          'npx cdk synth -q',
        ],
      }),
      codeBuildDefaults: {
        buildEnvironment: {
          buildImage: codebuild.LinuxBuildImage.STANDARD_7_0,
          environmentVariables: {
            CDK_DEFAULT_ACCOUNT: { value: '022074716478' },
            CDK_DEFAULT_REGION: { value: 'eu-west-2' },
          },
        },
      },
    });

    const prodStage = new TelemetryPipelineAppStage(this, 'Prod', {
      env: {
        account: '022074716478',
        region: 'eu-west-2',
      },
    });

    pipeline.addStage(prodStage);
  }
}
