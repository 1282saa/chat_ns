/*
 * News Chatbot API Stack
 *
 * 이 스택은 서울경제신문 뉴스 데이터를 기반으로 한 챗봇 API를 구현합니다.
 * 사용자의 질문을 받아 Bedrock Knowledge Base를 통해 관련 뉴스를 검색하고,
 * 생성형 AI를 활용하여 요약된 답변을 제공하는 서버리스 API를 제공합니다.
 *
 * 주요 구성요소:
 * - API Gateway: 외부 요청을 받는 REST API 엔드포인트
 * - Lambda Function: 챗봇 로직을 처리하는 서버리스 함수
 * - IAM Role: Bedrock Knowledge Base 접근 권한
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
import * as iam from "aws-cdk-lib/aws-iam";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import { PythonFunction } from "@aws-cdk/aws-lambda-python-alpha";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";
import { CommonStack } from "./common-stack";

export interface NewsChatbotApiStackProps extends StackProps {
  readonly commonStack: CommonStack;
  readonly knowledgeBaseId: string;
}

export class NewsChatbotApiStack extends Stack {
  public readonly chatbotApi: apigateway.RestApi;
  public readonly chatbotFunction: PythonFunction;

  constructor(scope: Construct, id: string, props: NewsChatbotApiStackProps) {
    super(scope, id, props);

    // IAM Role for Lambda function to access Bedrock
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
        PERPLEXITY_API_KEY:
          "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",
      },
      layers: [
        props.commonStack.LAYER_BOTO,
        props.commonStack.LAYER_POWERTOOLS,
      ],
      logRetention: logs.RetentionDays.ONE_WEEK,
    });

    // API Gateway for REST API
    this.chatbotApi = new apigateway.RestApi(this, "ChatbotApi", {
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

    // Lambda integration for API Gateway
    const lambdaIntegration = new apigateway.LambdaIntegration(
      this.chatbotFunction,
      {
        requestTemplates: { "application/json": '{ "statusCode": "200" }' },
        integrationResponses: [
          {
            statusCode: "200",
            responseParameters: {
              "method.response.header.Access-Control-Allow-Origin": "'*'",
            },
          },
        ],
      }
    );

    // API Gateway resources and methods
    const chatResource = this.chatbotApi.root.addResource("chat");
    chatResource.addMethod("POST", lambdaIntegration, {
      methodResponses: [
        {
          statusCode: "200",
          responseParameters: {
            "method.response.header.Access-Control-Allow-Origin": true,
          },
        },
      ],
    });

    // Health check endpoint
    const healthResource = this.chatbotApi.root.addResource("health");
    healthResource.addMethod("GET", lambdaIntegration);

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

    // CDK NAG suppressions for security compliance
    NagSuppressions.addResourceSuppressions(chatbotLambdaRole, [
      {
        id: "AwsSolutions-IAM5",
        reason:
          "Wildcard permissions are required for Bedrock foundation models access",
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
