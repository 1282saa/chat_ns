/*
 * News Chatbot Main Entry Point
 *
 * 이 파일은 뉴스 챗봇 API만을 위한 독립적인 CDK 애플리케이션 진입점입니다.
 * 기존 프로젝트의 복잡한 의존성 없이 뉴스 챗봇만 간단하게 배포할 수 있습니다.
 *
 * 사용법: cdk deploy --app "npx ts-node src/news-chatbot-main.ts"
 */

import { App, Tags } from "aws-cdk-lib";
import { NewsChatbotStandaloneStack } from "./stacks/news-chatbot-standalone-stack";

// CDK 애플리케이션 생성
const app = new App();

// 환경 설정
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || "ap-northeast-2",
};

// 지식 기반 ID (환경 변수 또는 기본값 사용)
const knowledgeBaseId =
  app.node.tryGetContext("knowledgeBaseId") || "PGQV3JXPET";

// 뉴스 챗봇 스택 생성
const newsChatbotStack = new NewsChatbotStandaloneStack(
  app,
  "NewsChatbotStack",
  {
    env: env,
    knowledgeBaseId: knowledgeBaseId,
    description: "News Chatbot API using Bedrock Knowledge Base",
    stackName: "NewsChatbotStack",
  }
);

// 태그 추가
Tags.of(app).add("Project", "News Chatbot");
Tags.of(app).add("Environment", "Production");
Tags.of(app).add("Owner", "Seoul Economic Daily");

// 애플리케이션 배포
app.synth();
