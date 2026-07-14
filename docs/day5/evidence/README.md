# Project Day5 증빙 목록

## 사전 완료 증빙

- `day5-local-verification.png`: Ruff lint/format, pytest 88개, 프런트 저장 회귀 4개, React production build, `.env` 제외, 실제 SSE 상태 이벤트
- `day5-training-fallback-ui.png`: 훈련 질문의 클라우드 직무 인식과 API 키 미설정 시 안전한 공식 검색 fallback
- `day5-housing-multiturn-ui.png`: 주거정책 질문의 조건 확인과 후속 답변 뒤 검색 재개

모든 캡처는 로컬 환경에서 생성했으며 API 키·인증 URL·사용자 민감정보를 포함하지 않는다.

추가 브라우저 회귀에서는 단일·다중 채팅 새로고침 복원, 새로고침 뒤 주거정책 후속 검색 재개, 개별·전체 기록 삭제를 확인했다.

## 수업 중 추가할 증빙

- Docker Desktop 실행 후 실제 이미지 build 성공 화면
- 외부 배포본 `/`, `/api/health`, `/docs` 확인 화면
- Langfuse 프로젝트·키를 직접 설정한 뒤 Trace 1건 화면

수업 중 추가 증빙까지 확인한 후 5일차 일일회고의 진행률을 `100%`로 확정한다.
