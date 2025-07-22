import * as cdk from 'aws-cdk-lib';
import * as apigateway from 'aws-cdk-lib/aws-apigateway';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { Construct } from 'constructs';
export interface NewsChatbotStackProps extends cdk.StackProps {
    perplexityApiKey: string;
    bigkindsApiKey: string;
}
export declare class NewsChatbotStack extends cdk.Stack {
    readonly api: apigateway.RestApi;
    readonly distribution: cloudfront.Distribution;
    readonly dataFetcherFunction: PythonFunction;
    constructor(scope: Construct, id: string, props: NewsChatbotStackProps);
}
