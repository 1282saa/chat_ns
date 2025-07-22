import * as cdk from 'aws-cdk-lib';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as secretsmanager from 'aws-cdk-lib/aws-secretsmanager';
import * as events from 'aws-cdk-lib/aws-events';
import * as targets from 'aws-cdk-lib/aws-events-targets';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { Construct } from 'constructs';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as path from 'path';

export interface NewsChatbotStackProps extends cdk.StackProps {
  perplexityApiKey: string;
  bigkindsApiKey: string;
}

export class NewsChatbotStack extends cdk.Stack {
  public readonly api: apigateway.RestApi;
  public readonly distribution: cloudfront.Distribution;
  public readonly dataFetcherFunction: PythonFunction;

  constructor(scope: Construct, id: string, props: NewsChatbotStackProps) {
    super(scope, id, props);

    // BigKinds API Key Secret
    const bigkindsSecret = new secretsmanager.Secret(this, 'BigKindsApiKeySecret', {
      secretName: 'BigKindsApiKeySecret',
      description: 'BigKinds API Key for automated news data collection',
      secretObjectValue: {
        BIGKINDS_API_KEY: cdk.SecretValue.unsafePlainText(props.bigkindsApiKey),
      },
    });

    // S3 Bucket for static website hosting
    const websiteBucket = new s3.Bucket(this, 'NewsChatbotWebsiteBucketV2', {
      bucketName: `news-chatbot-website-v2-${cdk.Aws.ACCOUNT_ID}`,
      websiteIndexDocument: 'index.html',
      publicReadAccess: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ACLS,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // S3 Bucket for news data storage
    const dataBucket = new s3.Bucket(this, 'NewsDataBucket', {
      bucketName: `seoul-economic-news-data-2025-${cdk.Aws.ACCOUNT_ID}`,
      versioned: true,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // IAM Role for Lambda functions
    const lambdaRole = new iam.Role(this, 'NewsChatbotLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        BedrockPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeModel',
                'bedrock:RetrieveAndGenerate',
                'bedrock:Retrieve',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });

    // IAM Role for Data Fetcher Lambda
    const dataFetcherLambdaRole = new iam.Role(this, 'DataFetcherLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        DataFetcherPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                's3:PutObject',
                's3:GetObject',
                's3:DeleteObject',
                's3:ListBucket',
              ],
              resources: [
                dataBucket.bucketArn,
                `${dataBucket.bucketArn}/*`,
              ],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'secretsmanager:GetSecretValue',
              ],
              resources: [bigkindsSecret.secretArn],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:StartIngestionJob',
                'bedrock:GetIngestionJob',
                'bedrock:ListIngestionJobs',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });

    // Main Chatbot Lambda Function
    const chatbotFunction = new PythonFunction(this, 'NewsChatbotFunction', {
      entry: path.join(__dirname, '../backend/news_chatbot'),
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'lambda_handler',
      timeout: cdk.Duration.minutes(5),
      memorySize: 1024,
      role: lambdaRole,
      environment: {
        PERPLEXITY_API_KEY: props.perplexityApiKey,
        KNOWLEDGE_BASE_ID: 'PGQV3JXPET',
        MODEL_ID: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
      },
    });

    // News Data Fetcher Lambda Function
    this.dataFetcherFunction = new PythonFunction(this, 'NewsDataFetcherFunction', {
      entry: path.join(__dirname, '../backend/news_fetcher'),
      runtime: lambda.Runtime.PYTHON_3_11,
      handler: 'lambda_handler',
      timeout: cdk.Duration.minutes(15),
      memorySize: 2048,
      role: dataFetcherLambdaRole,
      environment: {
        BIGKINDS_API_SECRET_ARN: bigkindsSecret.secretArn,
        DATA_BUCKET_NAME: dataBucket.bucketName,
        KNOWLEDGE_BASE_ID: 'PGQV3JXPET',
        DATA_SOURCE_ID: 'W8DS8YQGZG',
      },
    });

    // EventBridge Rule for scheduled execution (every 10 minutes)
    new events.Rule(this, 'NewsDataFetcherScheduleRule', {
      schedule: events.Schedule.rate(cdk.Duration.minutes(10)),
      targets: [new targets.LambdaFunction(this.dataFetcherFunction)],
      description: 'Trigger news data fetcher every 10 minutes',
    });

    // API Gateway
    this.api = new apigateway.RestApi(this, 'NewsChatbotApi', {
      restApiName: 'Seoul Economic News Chatbot API',
      description: 'API for Seoul Economic Daily News Chatbot',
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: ['Content-Type', 'X-Amz-Date', 'Authorization', 'X-Api-Key'],
      },
    });

    const chatIntegration = new apigateway.LambdaIntegration(chatbotFunction, {
      requestTemplates: { 'application/json': '{ "statusCode": "200" }' },
    });

    this.api.root.addResource('chat').addMethod('POST', chatIntegration);
    this.api.root.addResource('health').addMethod('GET', chatIntegration);

    // CloudFront Distribution
    this.distribution = new cloudfront.Distribution(this, 'NewsChatbotDistributionV2', {
      defaultBehavior: {
        origin: new origins.S3StaticWebsiteOrigin(websiteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED,
      },
      defaultRootObject: 'index.html',
      comment: 'Seoul Economic News Chatbot Distribution V2',
    });

    // Deploy website to S3
    new s3deploy.BucketDeployment(this, 'DeployWebsite', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../frontend'))],
      destinationBucket: websiteBucket,
      distribution: this.distribution,
      distributionPaths: ['/*'],
      prune: true,
    });

    // Outputs
    new cdk.CfnOutput(this, 'ApiUrl', {
      value: this.api.url,
      description: 'News Chatbot API URL',
    });

    new cdk.CfnOutput(this, 'WebsiteUrl', {
      value: `https://${this.distribution.domainName}`,
      description: 'News Chatbot Website URL',
    });

    new cdk.CfnOutput(this, 'BigKindsSecretArn', {
      value: bigkindsSecret.secretArn,
      description: 'BigKinds API Key Secret ARN',
    });
  }
}