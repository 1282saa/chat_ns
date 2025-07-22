/*
 * News Chatbot Standalone Stack
 *
 * 이 스택은 뉴스 챗봇 API를 위한 독립적인 배포 환경을 제공합니다.
 * 기존 CommonStack의 복잡한 의존성 없이 필요한 최소한의 리소스만 포함하여
 * 빠르고 간단하게 뉴스 챗봇을 배포할 수 있습니다.
 *
 * 주요 구성요소:
 * - Lambda Function: 챗봇 로직 처리
 * - API Gateway: REST API 엔드포인트
 * - IAM Role: Bedrock 및 S3 접근 권한
 * - CloudWatch Logs: 로깅
 */

import * as path from "path";
import {
  Stack,
  StackProps,
  Duration,
  CfnOutput,
  RemovalPolicy,
} from "aws-cdk-lib";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as s3deploy from "aws-cdk-lib/aws-s3-deployment";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";

export interface NewsChatbotStandaloneStackProps extends StackProps {
  readonly knowledgeBaseId: string;
}

export class NewsChatbotStandaloneStack extends Stack {
  public readonly chatbotApi: apigateway.RestApi;
  public readonly chatbotFunction: PythonFunction;
  public readonly api: apigateway.RestApi;

  constructor(
    scope: Construct,
    id: string,
    props: NewsChatbotStandaloneStackProps
  ) {
    super(scope, id, props);

    // IAM Role for Lambda function to access Bedrock and S3
    const chatbotLambdaRole = new iam.Role(this, "ChatbotLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      description: "IAM role for News Chatbot Lambda function",
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
      inlinePolicies: {
        BedrockKnowledgeBasePolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "bedrock:RetrieveAndGenerate",
                "bedrock:Retrieve",
                "bedrock:InvokeModel",
              ],
              resources: [
                `arn:aws:bedrock:${this.region}:${this.account}:knowledge-base/${props.knowledgeBaseId}`,
                "arn:aws:bedrock:*::foundation-model/*",
              ],
            }),
            // S3 읽기 권한 추가
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "s3:GetObject",
                "s3:GetObjectVersion",
              ],
              resources: [
                "arn:aws:s3:::seoul-economic-news-data-2025/*",
              ],
            }),
          ],
        }),
      },
    });

    // Lambda function for chatbot logic
    this.chatbotFunction = new PythonFunction(this, "ChatbotFunction", {
      entry: path.join(__dirname, "../backend/news_chatbot"),
      runtime: lambda.Runtime.PYTHON_3_11,
      architecture: lambda.Architecture.X86_64,
      handler: "handler",
      functionName: "news-chatbot-handler",
      description: "Handles chatbot requests using Bedrock Knowledge Base",
      timeout: Duration.minutes(5),
      memorySize: 1024,
      role: chatbotLambdaRole,
      environment: {
        KNOWLEDGE_BASE_ID: props.knowledgeBaseId,
        LOG_LEVEL: "INFO",
        PERPLEXITY_API_KEY: process.env.PERPLEXITY_API_KEY || "", // 환경 변수에서 가져오기
      },
      logRetention: logs.RetentionDays.ONE_WEEK,
    });

    // API Gateway for REST API
    this.api = this.chatbotApi = new apigateway.RestApi(this, "ChatbotApi", {
      restApiName: "News Chatbot API",
      description: "REST API for News Chatbot service",
      deployOptions: {
        stageName: "prod",
        loggingLevel: apigateway.MethodLoggingLevel.INFO,
        dataTraceEnabled: true,
        metricsEnabled: true,
        accessLogDestination: new apigateway.LogGroupLogDestination(
          new logs.LogGroup(this, "ChatbotApiAccessLogs", {
            retention: logs.RetentionDays.ONE_WEEK,
            removalPolicy: RemovalPolicy.DESTROY,
          })
        ),
        accessLogFormat: apigateway.AccessLogFormat.jsonWithStandardFields(),
      },
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
          "X-Amz-Security-Token",
        ],
      },
    });

    // Lambda integration for API Gateway (Proxy Integration)
    const lambdaIntegration = new apigateway.LambdaIntegration(
      this.chatbotFunction,
      {
        proxy: true, // Enable proxy integration for Lambda Powertools
      }
    );

    // API Gateway resources and methods
    const chatResource = this.chatbotApi.root.addResource("chat");
    chatResource.addMethod("POST", lambdaIntegration);

    // Health check endpoint
    const healthResource = this.chatbotApi.root.addResource("health");
    healthResource.addMethod("GET", lambdaIntegration);

    // S3 bucket for hosting the frontend
    const websiteBucket = new s3.Bucket(this, "WebsiteBucket", {
      bucketName: `news-chatbot-frontend-${this.account}-${this.region}`,
      publicReadAccess: true,
      websiteIndexDocument: "index.html",
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // Deploy frontend files to S3
    new s3deploy.BucketDeployment(this, "DeployWebsite", {
      sources: [s3deploy.Source.asset(path.join(__dirname, "../frontend"))],
      destinationBucket: websiteBucket,
      cacheControl: [
        s3deploy.CacheControl.setPublic(),
        s3deploy.CacheControl.maxAge(Duration.hours(1)),
      ],
    });

    // CloudFront distribution for the website
    const distribution = new cloudfront.CloudFrontWebDistribution(this, "WebsiteDistribution", {
      originConfigs: [
        {
          s3OriginSource: {
            s3BucketSource: websiteBucket,
          },
          behaviors: [{ isDefaultBehavior: true }],
        },
      ],
      defaultRootObject: "index.html",
      errorConfigurations: [
        {
          errorCode: 404,
          responseCode: 200,
          responsePagePath: "/index.html",
        },
      ],
    });

    // CloudFormation outputs
    new CfnOutput(this, "ChatbotApiUrl", {
      value: this.chatbotApi.url,
      description: "URL of the News Chatbot API",
      exportName: "NewsChatbotApiUrl",
    });

    new CfnOutput(this, "ChatbotFunctionName", {
      value: this.chatbotFunction.functionName,
      description: "Name of the News Chatbot Lambda function",
      exportName: "NewsChatbotFunctionName",
    });

    new CfnOutput(this, "KnowledgeBaseId", {
      value: props.knowledgeBaseId,
      description: "ID of the Bedrock Knowledge Base being used",
      exportName: "NewsChatbotKnowledgeBaseId",
    });

    new CfnOutput(this, "WebsiteUrl", {
      value: `https://${distribution.distributionDomainName}`,
      description: "Frontend Website URL",
      exportName: "NewsChatbotWebsiteUrl",
    });

    new CfnOutput(this, "WebsiteBucket", {
      value: websiteBucket.bucketName,
      description: "S3 Bucket for Frontend",
      exportName: "NewsChatbotWebsiteBucket",
    });

    // CDK NAG suppressions for security compliance
    NagSuppressions.addResourceSuppressions(chatbotLambdaRole, [
      {
        id: "AwsSolutions-IAM5",
        reason:
          "Wildcard permissions are required for Bedrock foundation models access and S3 object access",
      },
    ]);

    NagSuppressions.addResourceSuppressions(this.chatbotApi, [
      {
        id: "AwsSolutions-APIG2",
        reason: "Request validation is handled at the Lambda function level",
      },
      {
        id: "AwsSolutions-COG4",
        reason:
          "API Gateway authorization will be implemented in future phases",
      },
    ]);
  }
}
