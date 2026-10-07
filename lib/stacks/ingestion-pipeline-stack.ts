import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as sfn from 'aws-cdk-lib/aws-stepfunctions';
import * as tasks from 'aws-cdk-lib/aws-stepfunctions-tasks';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as appconfig from 'aws-cdk-lib/aws-appconfig';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as fs from 'fs';
import * as path from 'path';
import { Construct } from 'constructs';
import { DynamoTableConstruct } from '../constructs/dynamo-table';

export class IngestionPipelineStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const secretName = 'prod/withings/credentials';
    const secret = secretsmanager.Secret.fromSecretNameV2(this, 'WithingsSecret', secretName);
    const ddb = new DynamoTableConstruct(this, 'DynamoConstruct');

    // 1. AWS AppConfig Provisioning
    const app = new appconfig.CfnApplication(this, 'TelemetryAppConfig', {
      name: 'TelemetryIngestionApp',
    });

    const env = new appconfig.CfnEnvironment(this, 'TelemetryAppConfigEnv', {
      applicationId: app.ref,
      name: 'production',
      deletionProtectionCheck: 'BYPASS',
    });

    const configContent = fs.readFileSync(
      path.join(__dirname, '../../config/ingestion-config.json'),
      'utf-8'
    );

    const configProfile = new appconfig.CfnConfigurationProfile(this, 'TelemetryProfile', {
      applicationId: app.ref,
      name: 'IngestionSchedules',
      locationUri: 'hosted',
      deletionProtectionCheck: 'BYPASS',
    });

    const hostedVersion = new appconfig.CfnHostedConfigurationVersion(this, 'TelemetryHostedVer', {
      applicationId: app.ref,
      configurationProfileId: configProfile.ref,
      contentType: 'application/json',
      content: configContent,
    });

    new appconfig.CfnDeployment(this, 'TelemetryDeployment', {
      applicationId: app.ref,
      environmentId: env.ref,
      configurationProfileId: configProfile.ref,
      configurationVersion: hostedVersion.ref,
      deploymentStrategyId: 'AppConfig.AllAtOnce',
    });

    // 2. Token Refresher Function
    const tokenRefresherFn = new lambda.Function(this, 'TokenRefresherFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      code: lambda.Code.fromAsset('src/lambda/token_refresher'),
      handler: 'index.handler',
      timeout: cdk.Duration.seconds(30),
      environment: { SECRET_NAME: secretName },
    });
    secret.grantRead(tokenRefresherFn);
    secret.grantWrite(tokenRefresherFn);

    // 3. Router Lambda Function
    const routerSyncFn = new lambda.Function(this, 'RouterSyncFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      code: lambda.Code.fromAsset('src/lambda/router'),
      handler: 'index.handler',
      timeout: cdk.Duration.seconds(60),
      environment: { TABLE_NAME: ddb.table.tableName },
    });
    ddb.table.grantReadWriteData(routerSyncFn);

    // 4. Parameterized Step Functions State Machine
    const refreshTokenTask = new tasks.LambdaInvoke(this, 'ValidateOrRefreshTokensTask', {
      lambdaFunction: tokenRefresherFn,
      payload: sfn.TaskInput.fromObject({
        secret_name: sfn.JsonPath.stringAt('$.secret_name'),
      }),
      resultSelector: {
        'access_token.$': '$.Payload.access_token',
        'userid.$': '$.Payload.userid',
      },
      resultPath: '$.auth',
    });

    const routeAndSyncTask = new tasks.LambdaInvoke(this, 'RouteAndSyncTask', {
      lambdaFunction: routerSyncFn,
      payload: sfn.TaskInput.fromObject({
        provider: sfn.JsonPath.stringAt('$.provider'),
        endpoint: sfn.JsonPath.stringAt('$.endpoint'),
        endpoint_config: sfn.JsonPath.objectAt('$.endpoint_config'),
        access_token: sfn.JsonPath.stringAt('$.auth.access_token'),
        userid: sfn.JsonPath.stringAt('$.auth.userid'),
      }),
      outputPath: '$.Payload',
    });

    const chain = refreshTokenTask.next(routeAndSyncTask);

    const stateMachine = new sfn.StateMachine(this, 'UniversalIngestionPipeline', {
      stateMachineName: 'UniversalIngestionPipeline',
      definitionBody: sfn.DefinitionBody.fromChainable(chain),
      timeout: cdk.Duration.minutes(5),
      stateMachineType: sfn.StateMachineType.STANDARD,
    });

    // 5. Dispatcher Lambda (Native AppConfig SDK client)
    const dispatcherFn = new lambda.Function(this, 'DispatcherFn', {
      runtime: lambda.Runtime.PYTHON_3_12,
      code: lambda.Code.fromAsset('src/lambda/dispatcher'),
      handler: 'index.handler',
      timeout: cdk.Duration.seconds(30),
      environment: {
        APPCONFIG_APP: app.ref,
        APPCONFIG_ENV: env.ref,
        APPCONFIG_CONF: configProfile.ref,
        TABLE_NAME: ddb.table.tableName,
        STATE_MACHINE_ARN: stateMachine.stateMachineArn,
      },
    });

    dispatcherFn.addToRolePolicy(
      new iam.PolicyStatement({
        actions: [
          'appconfig:StartConfigurationSession',
          'appconfig:GetLatestConfiguration',
        ],
        resources: ['*'],
      })
    );
    ddb.table.grantReadWriteData(dispatcherFn);
    stateMachine.grantStartExecution(dispatcherFn);

    // 6. EventBridge Heartbeat (Every 5 minutes)
    new events.Rule(this, 'FiveMinuteHeartbeatRule', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(5)),
      targets: [new targets.LambdaFunction(dispatcherFn)],
    });
  }
}
