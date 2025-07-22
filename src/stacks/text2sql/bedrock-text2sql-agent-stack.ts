/*
* Copyright Amazon.com and its affiliates; all rights reserved.
* SPDX-License-Identifier: LicenseRef-.amazon.com.-AmznSL-1.0
* Licensed under the Amazon Software License  https://aws.amazon.com/asl/
*/

import { readFileSync } from "fs";
import * as path from "path";
import {
  PythonFunction,
  PythonLayerVersion,
} from "@aws-cdk/aws-lambda-python-alpha";
import {
  bedrock,
  BedrockCwDashboard,
} from "@cdklabs/generative-ai-cdk-constructs";
import {
  AgentActionGroup,
} from "@cdklabs/generative-ai-cdk-constructs/lib/cdk-lib/bedrock";
import { Stack, StackProps, Duration } from "aws-cdk-lib";
import * as iam from "aws-cdk-lib/aws-iam";
import { Runtime, LayerVersion, Code, IFunction } from "aws-cdk-lib/aws-lambda";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as cdk from "aws-cdk-lib/core";
import { NagSuppressions } from "cdk-nag";
import { Construct } from "constructs";

interface BedrockText2SqlAgentsStackProps extends StackProps {
  AGENT_KB: bedrock.IKnowledgeBase | null;
  LAYER_BOTO: PythonLayerVersion;
  LAYER_POWERTOOLS: PythonLayerVersion;
  LAYER_PYDANTIC: PythonLayerVersion;
  ATHENA_OUTPUT_BUCKET: s3.Bucket;
  ATHENA_DATA_BUCKET: s3.Bucket;
}

export class BedrockText2SqlAgentsStack extends Stack {
  public readonly ANTHROPIC_CLAUDE_AGENT: bedrock.Agent;
  public readonly ANTHROPIC_CLAUDE_AGENT_ALIAS: string;
  public readonly AMAZON_NOVA_AGENT: bedrock.Agent;
  public readonly AMAZON_NOVA_AGENT_ALIAS: string;

  constructor(
    scope: Construct,
    id: string,
    props: BedrockText2SqlAgentsStackProps,
  ) {
    super(scope, id, props);

    // Common Layer for Athena utilities
    const athenaCommonLayer = new LayerVersion(this, "AthenaCommonLayer", {
      code: Code.fromAsset(
        path.join(__dirname, "../../backend/agents/lambda/text2sql/athena/common"),
      ),
      description: "Common utilities for Athena operations",
      compatibleRuntimes: [Runtime.PYTHON_3_11],
    });

    // Define a function to create Athena Lambdas - 1. query execution, 2. schema read
    function createAthenaLambdaRole(
      parentScope: Construct,
      roleId: string,
      athenaDataBucket: s3.Bucket,
      athenaOutputBucket: s3.Bucket,
    ): iam.Role {
      const stack = Stack.of(parentScope);
      const role = new iam.Role(parentScope, roleId, {
        assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName(
            "service-role/AWSLambdaBasicExecutionRole",
          ),
        ],
      });

      role.addToPolicy(
        new iam.PolicyStatement({
          actions: [
            "athena:StartQueryExecution",
            "athena:GetQueryExecution",
            "athena:GetQueryResults",
          ],
          resources: [
            `arn:aws:athena:${stack.region}:${stack.account}:workgroup/primary`,
          ],
        }),
      );

      role.addToPolicy(
        new iam.PolicyStatement({
          actions: [
            "glue:GetDatabase",
            "glue:GetTable",
            "glue:GetTables",
            "glue:GetPartitions",
          ],
          resources: [
            `arn:aws:glue:${stack.region}:${stack.account}:catalog`,
            `arn:aws:glue:${stack.region}:${stack.account}:database/*`,
            `arn:aws:glue:${stack.region}:${stack.account}:table/*`,
          ],
        }),
      );

      role.addToPolicy(
        new iam.PolicyStatement({
          actions: [
            "s3:GetBucketLocation",
            "s3:GetObject",
            "s3:ListBucket",
            "s3:PutObject",
          ],
          resources: [
            athenaDataBucket.bucketArn,
            `${athenaDataBucket.bucketArn}/*`,
            athenaOutputBucket.bucketArn,
            `${athenaOutputBucket.bucketArn}/*`,
          ],
        }),
      );

      return role;
    }

    // Define a function to create Agent action group Lambdas
    function createLambdaFunction(
      parentScope: Construct,
      lambdaId: string,
      lambdaProps: {
        entry: string;
        fileName?: string;
        functionName?: string;
        role?: iam.Role;
        layers?: PythonLayerVersion[];
        environment?: { [key: string]: string };
        deadLetterQueue?: sqs.Queue;
      },
    ): PythonFunction {
      // Extract the file name, which is set to be same as the directory base name
      if (lambdaProps.fileName === undefined) {
        lambdaProps.fileName = path.basename(lambdaProps.entry) + ".py";
      }
      if (lambdaProps.functionName === undefined) {
        lambdaProps.functionName = `${path.parse(lambdaProps.fileName).name}-${id}`;
      }
      return new PythonFunction(parentScope, lambdaId, {
        functionName: lambdaProps.functionName,
        entry: lambdaProps.entry,
        index: lambdaProps.fileName,
        handler: "lambda_handler", // The handler name must be lambda_handler
        runtime: Runtime.PYTHON_3_11,
        timeout: Duration.minutes(5),
        memorySize: 256,
        environment: lambdaProps.environment,
        layers: lambdaProps.layers,
        role: lambdaProps.role,
        deadLetterQueue: lambdaProps.deadLetterQueue,
      });
    }

    // Define a function to create a Bedrock Agent action group
    function createAgentActionGroup(
      parentScope: Construct,
      agentId: string,
      agentProps: {
        actionGroupName: string;
        description: string;
        lambda: IFunction;
        openApiPath: string;
      },
    ): AgentActionGroup {
      return new AgentActionGroup({
        name: agentProps.actionGroupName,
        description: agentProps.description,
        executor: bedrock.ActionGroupExecutor.fromlambdaFunction(agentProps.lambda),
        apiSchema: bedrock.ApiSchema.fromLocalAsset(
          // openapi.json schema must be defined and stored under the path
          path.join(
            "src/backend/agents/lambda/text2sql/athena",
            agentProps.openApiPath,
            "openapi.json",
          ),
        ),
      });
    }

    // Get local prompts for Amazon Bedrock Agents
    function getPrompt(promptPath: string, promptName: string): string {
      return readFileSync(
        path.join(
          __dirname,
          promptPath,
          promptName,
        ),
        "utf8",
      );
    }

    // Amazon Bedrock Agent with Anthropic Claude Models
    const anthropicClaudeCrossRegionInferenceProfile = bedrock.CrossRegionInferenceProfile.fromConfig({
      geoRegion: bedrock.CrossRegionInferenceProfileRegion.APAC,
      model: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V2_0
    });
    
    const anthropicClaudeAgent = new bedrock.Agent(this, "AnthropicClaudeText2SqlAgent", {
      name: (cdk.Stack.of(this) + "-" + "AnthropicClaudeText2SqlAgent").replace("/", "-"),
      foundationModel: anthropicClaudeCrossRegionInferenceProfile,
      shouldPrepareAgent: true,
      userInputEnabled: true,
      codeInterpreterEnabled: false,
      instruction:
        "You are " +
        this.node.tryGetContext("custom:agentName") +
        ", a SQL analyst AI created specifically for " +
        this.node.tryGetContext("custom:companyName") +
        ". If Human says Hello, Great the human with your name." +
        "\n" +
        getPrompt("../../prompt/instruction/text2sql/anthropic/claude/sonnet3.5", "instruction.txt"),
      promptOverrideConfiguration: bedrock.PromptOverrideConfiguration.fromSteps(
        [
          {
            stepType: bedrock.AgentStepType.ORCHESTRATION,
            stepEnabled: true,
            customPromptTemplate: getPrompt("../../prompt/orchestration/text2sql/anthropic/claude/sonnet3.5", "orchestration_prompt.txt"),
            inferenceConfig: {
              temperature: 0,
              topP: 1,
              topK: 250,
              maximumLength: 2048,
              stopSequences: ["</invoke>", "</error>", "</answer>"],
            }
          }

        ]
      )
    });
    this.ANTHROPIC_CLAUDE_AGENT = anthropicClaudeAgent;

    // Amazon Bedrock Agent with Amazon Nova models
    const amazonNovaCrossRegionInferenceProfile = bedrock.CrossRegionInferenceProfile.fromConfig({
      geoRegion: bedrock.CrossRegionInferenceProfileRegion.APAC,
      model: bedrock.BedrockFoundationModel.AMAZON_NOVA_PRO_V1
    });
    const amazonNovaAgent = new bedrock.Agent(this, "AmazonNovaText2SqlAgent", {
      name: (cdk.Stack.of(this) + "-" + "AmazonNovaText2SqlAgent").replace("/", "-"),
      // foundationModel: bedrock.BedrockFoundationModel.fromCdkFoundationModelId(new FoundationModelIdentifier("us.amazon.nova-pro-v1:0")), // Using US Cross-region inference profile
      foundationModel: amazonNovaCrossRegionInferenceProfile,
      shouldPrepareAgent: true,
      userInputEnabled: true,
      codeInterpreterEnabled: false,
      instruction:
        "You are " +
        this.node.tryGetContext("custom:agentName") +
        ", a SQL analyst AI created specifically for " +
        this.node.tryGetContext("custom:companyName") +
        ". If Human says Hello, Great the human with your name." +
        "\n" +
        getPrompt("../../prompt/instruction/text2sql/amazon/nova/pro1.0", "instruction.txt"),
      promptOverrideConfiguration: bedrock.PromptOverrideConfiguration.fromSteps(
        [
          {
            stepType: bedrock.AgentStepType.ORCHESTRATION,
            stepEnabled: true,
            customPromptTemplate: getPrompt("../../prompt/orchestration/text2sql/amazon/nova/pro1.0", "orchestration_prompt.txt"),
            inferenceConfig: {
              temperature: 0,
              topP: 1,
              topK: 128,
              maximumLength: 2048,
              stopSequences: ["</answer>", "\n\n<thinking>", "\n<thinking>", " <thinking>"],
            }
          }

        ]
      )
    });
    this.AMAZON_NOVA_AGENT = amazonNovaAgent;

    // Create IAM role for Athena Schema Reader Lambda
    const athenaSchemaReaderRole = createAthenaLambdaRole(
      this,
      "AthenaSchemaReaderRole",
      props.ATHENA_DATA_BUCKET,
      props.ATHENA_OUTPUT_BUCKET,
    );

    // Create Athena Schema Reader Lambda for Anthropic Claude Agent
    const anthropicClaudeAthenaSchemaReaderLambda = createLambdaFunction(
      this,
      "AnthropicClaudeAthenaSchemaReaderLambda",
      {
        entry: path.join(
          "src/backend/agents/lambda/text2sql/athena",
          "athena_schema_reader",
          "claude",
        ),
        functionName: "claude_athena_schema_reader",
        fileName: "athena_schema_reader.py",
        role: athenaSchemaReaderRole,
        layers: [
          props.LAYER_BOTO,
          props.LAYER_POWERTOOLS,
          props.LAYER_PYDANTIC,
          athenaCommonLayer,
        ],
        environment: {
          S3_OUTPUT: props.ATHENA_OUTPUT_BUCKET.bucketName,
          S3_DATA_BUCKET: props.ATHENA_DATA_BUCKET.bucketName,
        },
      },
    );

    // Create Athena Schema Reader Lambda for Amazon Nova Agent
    const amazonNovaAthenaSchemaReaderLambda = createLambdaFunction(
      this,
      "AmazonNovaAthenaSchemaReaderLambda",
      {
        entry: path.join(
          "src/backend/agents/lambda/text2sql/athena",
          "athena_schema_reader",
          "nova",
        ),
        functionName: "nova_athena_schema_reader",
        fileName: "athena_schema_reader.py",
        role: athenaSchemaReaderRole,
        layers: [
          props.LAYER_BOTO,
          props.LAYER_POWERTOOLS,
          props.LAYER_PYDANTIC,
          athenaCommonLayer,
        ],
        environment: {
          S3_OUTPUT: props.ATHENA_OUTPUT_BUCKET.bucketName,
          S3_DATA_BUCKET: props.ATHENA_DATA_BUCKET.bucketName,
        },
      },
    );

    // Create DLQ for Athena Query Lambda
    const athenaQueryLambdaDLQ = new sqs.Queue(this, "AthenaQueryLambdaDLQ", {
      queueName: `AthenaQueryLambdaDLQs-${this.account}-${this.region}`,
      encryption: sqs.QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
    });

    // Create IAM role for Athena Query Execution Lambda
    const athenaQueryLambdaRole = createAthenaLambdaRole(
      this,
      "AthenaQueryLambdaRole",
      props.ATHENA_DATA_BUCKET,
      props.ATHENA_OUTPUT_BUCKET,
    );
    athenaQueryLambdaRole.addToPolicy(
      new iam.PolicyStatement({
        actions: ["sqs:SendMessage"],
        resources: [athenaQueryLambdaDLQ.queueArn],
      }),
    );

    // Create Athena Query Execution Lambda for Anthropic Claude Agent
    const anthropicClaudeAthenaQueryLambda = createLambdaFunction(this, "AnthropicClaudeAthenaQueryLambda", {
      entry: path.join(
        "src/backend/agents/lambda/text2sql/athena",
        "athena_actions",
        "claude"
      ),
      functionName: "claude_athena_actions",
      fileName: "athena_actions.py",
      role: athenaQueryLambdaRole,
      layers: [
        props.LAYER_BOTO,
        props.LAYER_POWERTOOLS,
        props.LAYER_PYDANTIC,
        athenaCommonLayer,
      ],
      environment: {
        S3_OUTPUT: props.ATHENA_OUTPUT_BUCKET.bucketName,
        S3_DATA_BUCKET: props.ATHENA_DATA_BUCKET.bucketName,
      },
      deadLetterQueue: athenaQueryLambdaDLQ,
    });

    // Create Athena Query Execution Lambda for Amazon Nova Agent
    const amazonNovaAthenaQueryLambda = createLambdaFunction(this, "AmazonNovaAthenaQueryLambda", {
      entry: path.join(
        "src/backend/agents/lambda/text2sql/athena",
        "athena_actions",
        "nova"
      ),
      functionName: "nova_athena_actions",
      fileName: "athena_actions.py",
      role: athenaQueryLambdaRole,
      layers: [
        props.LAYER_BOTO,
        props.LAYER_POWERTOOLS,
        props.LAYER_PYDANTIC,
        athenaCommonLayer,
      ],
      environment: {
        S3_OUTPUT: props.ATHENA_OUTPUT_BUCKET.bucketName,
        S3_DATA_BUCKET: props.ATHENA_DATA_BUCKET.bucketName,
      },
      deadLetterQueue: athenaQueryLambdaDLQ,
    });

    // Grant permissions to the Lambda functions
    props.ATHENA_DATA_BUCKET.grantReadWrite(
      anthropicClaudeAthenaQueryLambda,
      anthropicClaudeAthenaSchemaReaderLambda
    );
    props.ATHENA_OUTPUT_BUCKET.grantReadWrite(
      anthropicClaudeAthenaQueryLambda,
      anthropicClaudeAthenaSchemaReaderLambda
    );
    props.ATHENA_DATA_BUCKET.grantReadWrite(
      amazonNovaAthenaQueryLambda,
      amazonNovaAthenaSchemaReaderLambda
    );
    props.ATHENA_OUTPUT_BUCKET.grantReadWrite(
      amazonNovaAthenaQueryLambda,
      amazonNovaAthenaSchemaReaderLambda
    );

    // Add Athena Query Action Group
    const anthropicClaudeAthenaQueryActionGroup = createAgentActionGroup(
      this,
      "AnthropicClaudeAthenaQueryActionGroup",
      {
        actionGroupName: "athena_query_claude",
        description:
          "This action group is used to query information about data",
        lambda: anthropicClaudeAthenaQueryLambda,
        openApiPath: "athena_actions/claude",
      }
    );
    anthropicClaudeAgent.addActionGroup(anthropicClaudeAthenaQueryActionGroup);

    const amazonNovaAthenaQueryActionGroup = createAgentActionGroup(
      this,
      "AmazonNovaAthenaQueryActionGroup",
      {
        actionGroupName: "athena_query_nova",
        description:
          "This action group is used to query information about data",
        lambda: amazonNovaAthenaQueryLambda,
        openApiPath: "athena_actions/nova",
      }
    );
    amazonNovaAgent.addActionGroup(amazonNovaAthenaQueryActionGroup);

    // Add Athena Schema Reader Action Group
    const anthropicClaudeAthenaSchemaReaderActionGroup = createAgentActionGroup(
      this,
      "AnthropicClaudeAthenaSchemaReaderActionGroup",
      {
        actionGroupName: "athena_schema_reader_claude",
        description: "This action group is used to read schema from Athena",
        lambda: anthropicClaudeAthenaSchemaReaderLambda,
        openApiPath: "athena_schema_reader/claude",
      },
    );
    anthropicClaudeAgent.addActionGroup(anthropicClaudeAthenaSchemaReaderActionGroup);


    const amazonNovaAthenaSchemaReaderActionGroup = createAgentActionGroup(
      this,
      "AmazonNovaAthenaSchemaReaderActionGroup",
      {
        actionGroupName: "athena_schema_reader_nova",
        description: "This action group is used to read schema from Athena",
        lambda: amazonNovaAthenaSchemaReaderLambda,
        openApiPath: "athena_schema_reader/nova",
      },
    );
    amazonNovaAgent.addActionGroup(amazonNovaAthenaSchemaReaderActionGroup);

    // Create Bedrock Agent Alias for Anthropic Claude Agent
    const anthropicClaudeAthenaAgentAlias = new bedrock.AgentAlias(this, "AnthropicClaudeAgentAlias", {
      agent: anthropicClaudeAgent,
      aliasName: "latest",
    });
    this.ANTHROPIC_CLAUDE_AGENT_ALIAS = anthropicClaudeAthenaAgentAlias.aliasId;

    // Create Bedrock Agent Alias for Amazon Nova Agent
    const amazonNovaAthenaAgentAlias = new bedrock.AgentAlias(this, "AmazonNovaAgentAlias", {
      agent: amazonNovaAgent,
      aliasName: "latest",
    });
    this.AMAZON_NOVA_AGENT_ALIAS = amazonNovaAthenaAgentAlias.aliasId;

    // Create CloudWatch Dashboard for Bedrock
    const bedrockCwDashboard = new BedrockCwDashboard(
      this,
      "BedrockDashboardConstructText2sql",
      {
        dashboardName: "CSC_GenAI_LAB_Developer_Workshop_Dashboard_Text2Sql",
      },
    );

    // provides monitoring of all models
    bedrockCwDashboard.addAllModelsMonitoring();

    // provides monitoring for a specific model with on-demand pricing calculation
    // pricing details are available here: https://aws.amazon.com/bedrock/pricing/
    const knowledgeBase = props.AGENT_KB;
    if (knowledgeBase) {
      // Add Knowledge Base to the agent
      anthropicClaudeAgent.addKnowledgeBase(knowledgeBase);

      // Embeddings model monitoring specific to Knowledge Base scenario
      bedrockCwDashboard.addModelMonitoring(
        "Amazon Titan Text Embeddings v2.0",
        bedrock.BedrockFoundationModel.TITAN_EMBED_TEXT_V2_1024.modelArn,
        {
          inputTokenPrice: 0.00002,
          outputTokenPrice: 0, // N/A for Amazon Titan Text Embeddings V1 and V2
        },
      );
    }

    bedrockCwDashboard.addModelMonitoring(
      `Anthropic Claude Sonnet 3.5 v2.0 - ${bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V2_0.modelArn}`,
      bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_SONNET_V2_0.modelArn,
      {
        inputTokenPrice: 0.003, // On-demand Price per 1K input tokens
        outputTokenPrice: 0.015, // Price per 1K output tokens
      },
    );

    bedrockCwDashboard.addModelMonitoring(
      `Amazon Nova Pro v1.0  - ${bedrock.BedrockFoundationModel.AMAZON_NOVA_PRO_V1}`,
      bedrock.BedrockFoundationModel.AMAZON_NOVA_PRO_V1.modelArn,
      {
        inputTokenPrice: 0.0008, // On-demand Price per 1K input tokens
        outputTokenPrice: 0.0032, // Price per 1K output tokens
      },
    );

    bedrockCwDashboard.addModelMonitoring(
      `Anthropic Claude Haiku 3.5 v1.0 - ${bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_HAIKU_V1_0.modelArn}`,
      bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_3_5_HAIKU_V1_0.modelArn,
      {
        inputTokenPrice: 0.0008, // On-demand Price per 1K input tokens
        outputTokenPrice: 0.004, // Price per 1K output tokens
      },
    );

    // Suppress CDK-nag warnings
    NagSuppressions.addResourceSuppressions(
      athenaQueryLambdaDLQ,
      [
        {
          id: "AwsSolutions-SQS3",
          reason: "DLQ does not require server-side encryption with KMS",
        },
      ],
      true,
    );
  }
}
