/*
* Copyright Amazon.com and its affiliates; all rights reserved.
* SPDX-License-Identifier: LicenseRef-.amazon.com.-AmznSL-1.0
* Licensed under the Amazon Software License  https://aws.amazon.com/asl/
*/

import { bedrock } from "@cdklabs/generative-ai-cdk-constructs";

/**
 * Valid parser strategy codes
 */
export const VALID_PARSER_STRATEGIES = ['DEFAULT', 'FOUNDATION_MODEL', 'DATA_AUTOMATION'] as const;

/**
 * Parser strategy code type
 */
export type ParserStrategyCode = typeof VALID_PARSER_STRATEGIES[number];

/**
 * Parser strategy utility
 */
export class ParserStrategyUtil {
  /**
   * Validate if parser strategy code is valid
   */
  static isValid(code: string): code is ParserStrategyCode {
    return VALID_PARSER_STRATEGIES.includes(code as ParserStrategyCode);
  }

  /**
   * Create parsing strategy object based on parser strategy code
   */
  static createStrategy(code: ParserStrategyCode): bedrock.ParsingStategy | undefined {
    switch (code) {
      case 'FOUNDATION_MODEL':
        return bedrock.ParsingStategy.foundationModel({
          parsingModel: bedrock.BedrockFoundationModel.ANTHROPIC_CLAUDE_HAIKU_V1_0,
        });
        
      case 'DATA_AUTOMATION':
        console.log("Data Automation 파서 전략은 아직 구현되지 않았습니다.");
        return undefined;
        
      case 'DEFAULT':
      default:
        return undefined;
    }
  }
} 