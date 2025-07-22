import { App } from "aws-cdk-lib";
import { Template } from "aws-cdk-lib/assertions";
import { NewsChatbotStandaloneStack } from "../src/stacks/news-chatbot-standalone-stack";

describe("News Chatbot Stack Tests", () => {
  test("Stack creates successfully", () => {
    const app = new App();
    
    // Create the stack
    const stack = new NewsChatbotStandaloneStack(app, "TestNewsChatbotStack", {
      knowledgeBaseId: "test-kb-id",
      env: {
        account: "123456789012",
        region: "ap-northeast-2",
      },
    });

    // Get the CloudFormation template
    const template = Template.fromStack(stack);

    // Verify Lambda function is created
    template.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: "news-chatbot-handler",
      Runtime: "python3.11",
      MemorySize: 1024,
    });

    // Verify API Gateway is created
    template.hasResourceProperties("AWS::ApiGateway::RestApi", {
      Name: "News Chatbot API",
    });

    // Verify IAM role has correct permissions
    template.hasResourceProperties("AWS::IAM::Role", {
      AssumeRolePolicyDocument: {
        Statement: [{
          Effect: "Allow",
          Principal: {
            Service: "lambda.amazonaws.com"
          },
          Action: "sts:AssumeRole"
        }]
      }
    });
  });

  test("Stack has required outputs", () => {
    const app = new App();
    
    const stack = new NewsChatbotStandaloneStack(app, "TestStackWithOutputs", {
      knowledgeBaseId: "test-kb-id",
    });

    const template = Template.fromStack(stack);

    // Check for required outputs
    template.hasOutput("ChatbotApiUrl", {});
    template.hasOutput("ChatbotFunctionName", {});
    template.hasOutput("KnowledgeBaseId", {});
  });

  test("Environment variables are set correctly", () => {
    const app = new App();
    process.env.PERPLEXITY_API_KEY = "test-key";
    
    const stack = new NewsChatbotStandaloneStack(app, "TestEnvVarStack", {
      knowledgeBaseId: "test-kb-id",
    });

    const template = Template.fromStack(stack);

    // Verify environment variables
    template.hasResourceProperties("AWS::Lambda::Function", {
      Environment: {
        Variables: {
          KNOWLEDGE_BASE_ID: "test-kb-id",
          LOG_LEVEL: "INFO",
          PERPLEXITY_API_KEY: "test-key"
        }
      }
    });
  });
});