"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const cdk = require("aws-cdk-lib");
const assertions_1 = require("aws-cdk-lib/assertions");
const news_chatbot_standalone_stack_1 = require("../src/stacks/news-chatbot-standalone-stack");
describe('NewsChatbotStack', () => {
    test('creates all required resources', () => {
        const app = new cdk.App();
        const stack = new news_chatbot_standalone_stack_1.NewsChatbotStack(app, 'TestNewsChatbotStack', {
            perplexityApiKey: 'test-key',
            bigkindsApiKey: 'test-bigkinds-key',
        });
        const template = assertions_1.Template.fromStack(stack);
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
        const stack = new news_chatbot_standalone_stack_1.NewsChatbotStack(app, 'TestNewsChatbotStack', {
            perplexityApiKey: 'test-perplexity-key',
            bigkindsApiKey: 'test-bigkinds-key',
        });
        const template = assertions_1.Template.fromStack(stack);
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
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoibmV3cy1jaGF0Ym90LnRlc3QuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyJuZXdzLWNoYXRib3QudGVzdC50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiOztBQUFBLG1DQUFtQztBQUNuQyx1REFBa0Q7QUFDbEQsK0ZBQStFO0FBRS9FLFFBQVEsQ0FBQyxrQkFBa0IsRUFBRSxHQUFHLEVBQUU7SUFDaEMsSUFBSSxDQUFDLGdDQUFnQyxFQUFFLEdBQUcsRUFBRTtRQUMxQyxNQUFNLEdBQUcsR0FBRyxJQUFJLEdBQUcsQ0FBQyxHQUFHLEVBQUUsQ0FBQztRQUMxQixNQUFNLEtBQUssR0FBRyxJQUFJLGdEQUFnQixDQUFDLEdBQUcsRUFBRSxzQkFBc0IsRUFBRTtZQUM5RCxnQkFBZ0IsRUFBRSxVQUFVO1lBQzVCLGNBQWMsRUFBRSxtQkFBbUI7U0FDcEMsQ0FBQyxDQUFDO1FBRUgsTUFBTSxRQUFRLEdBQUcscUJBQVEsQ0FBQyxTQUFTLENBQUMsS0FBSyxDQUFDLENBQUM7UUFFM0Msd0NBQXdDO1FBQ3hDLFFBQVEsQ0FBQyxxQkFBcUIsQ0FBQyx1QkFBdUIsRUFBRTtZQUN0RCxPQUFPLEVBQUUsWUFBWTtTQUN0QixDQUFDLENBQUM7UUFFSCxrQ0FBa0M7UUFDbEMsUUFBUSxDQUFDLHFCQUFxQixDQUFDLDBCQUEwQixFQUFFO1lBQ3pELElBQUksRUFBRSxpQ0FBaUM7U0FDeEMsQ0FBQyxDQUFDO1FBRUgsa0NBQWtDO1FBQ2xDLFFBQVEsQ0FBQyxxQkFBcUIsQ0FBQyxpQkFBaUIsRUFBRSxFQUFFLENBQUMsQ0FBQztRQUV0RCw4Q0FBOEM7UUFDOUMsUUFBUSxDQUFDLHFCQUFxQixDQUFDLCtCQUErQixFQUFFLEVBQUUsQ0FBQyxDQUFDO1FBRXBFLDZDQUE2QztRQUM3QyxRQUFRLENBQUMscUJBQXFCLENBQUMsNkJBQTZCLEVBQUU7WUFDNUQsSUFBSSxFQUFFLHNCQUFzQjtTQUM3QixDQUFDLENBQUM7UUFFSCx1Q0FBdUM7UUFDdkMsUUFBUSxDQUFDLHFCQUFxQixDQUFDLG1CQUFtQixFQUFFO1lBQ2xELGtCQUFrQixFQUFFLGtCQUFrQjtTQUN2QyxDQUFDLENBQUM7SUFDTCxDQUFDLENBQUMsQ0FBQztJQUVILElBQUksQ0FBQyxtREFBbUQsRUFBRSxHQUFHLEVBQUU7UUFDN0QsTUFBTSxHQUFHLEdBQUcsSUFBSSxHQUFHLENBQUMsR0FBRyxFQUFFLENBQUM7UUFDMUIsTUFBTSxLQUFLLEdBQUcsSUFBSSxnREFBZ0IsQ0FBQyxHQUFHLEVBQUUsc0JBQXNCLEVBQUU7WUFDOUQsZ0JBQWdCLEVBQUUscUJBQXFCO1lBQ3ZDLGNBQWMsRUFBRSxtQkFBbUI7U0FDcEMsQ0FBQyxDQUFDO1FBRUgsTUFBTSxRQUFRLEdBQUcscUJBQVEsQ0FBQyxTQUFTLENBQUMsS0FBSyxDQUFDLENBQUM7UUFFM0MsUUFBUSxDQUFDLHFCQUFxQixDQUFDLHVCQUF1QixFQUFFO1lBQ3RELFdBQVcsRUFBRTtnQkFDWCxTQUFTLEVBQUU7b0JBQ1Qsa0JBQWtCLEVBQUUscUJBQXFCO29CQUN6QyxpQkFBaUIsRUFBRSxZQUFZO29CQUMvQixRQUFRLEVBQUUsMkNBQTJDO2lCQUN0RDthQUNGO1NBQ0YsQ0FBQyxDQUFDO0lBQ0wsQ0FBQyxDQUFDLENBQUM7QUFDTCxDQUFDLENBQUMsQ0FBQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgeyBUZW1wbGF0ZSB9IGZyb20gJ2F3cy1jZGstbGliL2Fzc2VydGlvbnMnO1xuaW1wb3J0IHsgTmV3c0NoYXRib3RTdGFjayB9IGZyb20gJy4uL3NyYy9zdGFja3MvbmV3cy1jaGF0Ym90LXN0YW5kYWxvbmUtc3RhY2snO1xuXG5kZXNjcmliZSgnTmV3c0NoYXRib3RTdGFjaycsICgpID0+IHtcbiAgdGVzdCgnY3JlYXRlcyBhbGwgcmVxdWlyZWQgcmVzb3VyY2VzJywgKCkgPT4ge1xuICAgIGNvbnN0IGFwcCA9IG5ldyBjZGsuQXBwKCk7XG4gICAgY29uc3Qgc3RhY2sgPSBuZXcgTmV3c0NoYXRib3RTdGFjayhhcHAsICdUZXN0TmV3c0NoYXRib3RTdGFjaycsIHtcbiAgICAgIHBlcnBsZXhpdHlBcGlLZXk6ICd0ZXN0LWtleScsXG4gICAgICBiaWdraW5kc0FwaUtleTogJ3Rlc3QtYmlna2luZHMta2V5JyxcbiAgICB9KTtcblxuICAgIGNvbnN0IHRlbXBsYXRlID0gVGVtcGxhdGUuZnJvbVN0YWNrKHN0YWNrKTtcblxuICAgIC8vIENoZWNrIGlmIExhbWJkYSBmdW5jdGlvbnMgYXJlIGNyZWF0ZWRcbiAgICB0ZW1wbGF0ZS5oYXNSZXNvdXJjZVByb3BlcnRpZXMoJ0FXUzo6TGFtYmRhOjpGdW5jdGlvbicsIHtcbiAgICAgIFJ1bnRpbWU6ICdweXRob24zLjExJyxcbiAgICB9KTtcblxuICAgIC8vIENoZWNrIGlmIEFQSSBHYXRld2F5IGlzIGNyZWF0ZWRcbiAgICB0ZW1wbGF0ZS5oYXNSZXNvdXJjZVByb3BlcnRpZXMoJ0FXUzo6QXBpR2F0ZXdheTo6UmVzdEFwaScsIHtcbiAgICAgIE5hbWU6ICdTZW91bCBFY29ub21pYyBOZXdzIENoYXRib3QgQVBJJyxcbiAgICB9KTtcblxuICAgIC8vIENoZWNrIGlmIFMzIGJ1Y2tldHMgYXJlIGNyZWF0ZWRcbiAgICB0ZW1wbGF0ZS5oYXNSZXNvdXJjZVByb3BlcnRpZXMoJ0FXUzo6UzM6OkJ1Y2tldCcsIHt9KTtcblxuICAgIC8vIENoZWNrIGlmIENsb3VkRnJvbnQgZGlzdHJpYnV0aW9uIGlzIGNyZWF0ZWRcbiAgICB0ZW1wbGF0ZS5oYXNSZXNvdXJjZVByb3BlcnRpZXMoJ0FXUzo6Q2xvdWRGcm9udDo6RGlzdHJpYnV0aW9uJywge30pO1xuXG4gICAgLy8gQ2hlY2sgaWYgU2VjcmV0cyBNYW5hZ2VyIHNlY3JldCBpcyBjcmVhdGVkXG4gICAgdGVtcGxhdGUuaGFzUmVzb3VyY2VQcm9wZXJ0aWVzKCdBV1M6OlNlY3JldHNNYW5hZ2VyOjpTZWNyZXQnLCB7XG4gICAgICBOYW1lOiAnQmlnS2luZHNBcGlLZXlTZWNyZXQnLFxuICAgIH0pO1xuXG4gICAgLy8gQ2hlY2sgaWYgRXZlbnRCcmlkZ2UgcnVsZSBpcyBjcmVhdGVkXG4gICAgdGVtcGxhdGUuaGFzUmVzb3VyY2VQcm9wZXJ0aWVzKCdBV1M6OkV2ZW50czo6UnVsZScsIHtcbiAgICAgIFNjaGVkdWxlRXhwcmVzc2lvbjogJ3JhdGUoMTAgbWludXRlcyknLFxuICAgIH0pO1xuICB9KTtcblxuICB0ZXN0KCdMYW1iZGEgZnVuY3Rpb24gaGFzIGNvcnJlY3QgZW52aXJvbm1lbnQgdmFyaWFibGVzJywgKCkgPT4ge1xuICAgIGNvbnN0IGFwcCA9IG5ldyBjZGsuQXBwKCk7XG4gICAgY29uc3Qgc3RhY2sgPSBuZXcgTmV3c0NoYXRib3RTdGFjayhhcHAsICdUZXN0TmV3c0NoYXRib3RTdGFjaycsIHtcbiAgICAgIHBlcnBsZXhpdHlBcGlLZXk6ICd0ZXN0LXBlcnBsZXhpdHkta2V5JyxcbiAgICAgIGJpZ2tpbmRzQXBpS2V5OiAndGVzdC1iaWdraW5kcy1rZXknLFxuICAgIH0pO1xuXG4gICAgY29uc3QgdGVtcGxhdGUgPSBUZW1wbGF0ZS5mcm9tU3RhY2soc3RhY2spO1xuXG4gICAgdGVtcGxhdGUuaGFzUmVzb3VyY2VQcm9wZXJ0aWVzKCdBV1M6OkxhbWJkYTo6RnVuY3Rpb24nLCB7XG4gICAgICBFbnZpcm9ubWVudDoge1xuICAgICAgICBWYXJpYWJsZXM6IHtcbiAgICAgICAgICBQRVJQTEVYSVRZX0FQSV9LRVk6ICd0ZXN0LXBlcnBsZXhpdHkta2V5JyxcbiAgICAgICAgICBLTk9XTEVER0VfQkFTRV9JRDogJ1BHUVYzSlhQRVQnLFxuICAgICAgICAgIE1PREVMX0lEOiAnYW50aHJvcGljLmNsYXVkZS0zLTUtc29ubmV0LTIwMjQxMDIyLXYyOjAnLFxuICAgICAgICB9LFxuICAgICAgfSxcbiAgICB9KTtcbiAgfSk7XG59KTsiXX0=