#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { NewsChatbotStack } from './stacks/news-chatbot-standalone-stack';

const app = new cdk.App();

const perplexityApiKey = process.env.PERPLEXITY_API_KEY;
if (!perplexityApiKey) {
  throw new Error('PERPLEXITY_API_KEY environment variable is required');
}

const bigkindsApiKey = '254bec69-1c13-470f-904a-c4bc9e46cc80';

new NewsChatbotStack(app, 'NewsChatbotStack', {
  perplexityApiKey,
  bigkindsApiKey,
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'ap-northeast-2',
  },
});