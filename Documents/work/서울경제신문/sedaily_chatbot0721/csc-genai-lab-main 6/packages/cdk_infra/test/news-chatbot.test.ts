import * as cdk from 'aws-cdk-lib';
import { Template } from 'aws-cdk-lib/assertions';
import { NewsChatbotStack } from '../src/stacks/news-chatbot-standalone-stack';

describe('NewsChatbotStack', () => {
  test('creates all required resources', () => {
    const app = new cdk.App();
    const stack = new NewsChatbotStack(app, 'TestNewsChatbotStack', {
      perplexityApiKey: 'test-key',
      bigkindsApiKey: 'test-bigkinds-key',
    });

    const template = Template.fromStack(stack);

    // Check if Lambda functions are created
    template.hasResourceProperties('AWS::Lambda::Function', {
      Runtime: 'python3.11',
    });

    // Check if API Gateway is created
    template.hasResourceProperties('AWS::ApiGateway::RestApi', {
      Name: 'Seoul Economic News Chatbot API',
    });

    // Check if S3 buckets are created
    template.hasResourceProperties('AWS::S3::Bucket', {});

    // Check if CloudFront distribution is created
    template.hasResourceProperties('AWS::CloudFront::Distribution', {});

    // Check if Secrets Manager secret is created
    template.hasResourceProperties('AWS::SecretsManager::Secret', {
      Name: 'BigKindsApiKeySecret',
    });

    // Check if EventBridge rule is created
    template.hasResourceProperties('AWS::Events::Rule', {
      ScheduleExpression: 'rate(10 minutes)',
    });
  });

  test('Lambda function has correct environment variables', () => {
    const app = new cdk.App();
    const stack = new NewsChatbotStack(app, 'TestNewsChatbotStack', {
      perplexityApiKey: 'test-perplexity-key',
      bigkindsApiKey: 'test-bigkinds-key',
    });

    const template = Template.fromStack(stack);

    template.hasResourceProperties('AWS::Lambda::Function', {
      Environment: {
        Variables: {
          PERPLEXITY_API_KEY: 'test-perplexity-key',
          KNOWLEDGE_BASE_ID: 'PGQV3JXPET',
          MODEL_ID: 'anthropic.claude-3-5-sonnet-20241022-v2:0',
        },
      },
    });
  });
});