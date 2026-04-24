# P14_DEPLOY — 배포 가능 패키징

## Phase 목표

프로젝트를 누구나 설치·실행 가능한 상태로 패키징.
pyproject.toml, config.example.yaml, env.example,
hermes-memory-doctor CLI, README.md 완성.

## 진입 선행조건

- Phase 13 E2E 통과
- 전 Phase 산출물 안정화
- 00_CORE 상시 첨부

## 수용 기준

- [ ] pyproject.toml — PEP 621, core + optional extras, console script
- [ ] config.example.yaml — 전체 스키마 예시 + 주석
- [ ] env.example — 모든 환경변수 placeholder
- [ ] cli/doctor.py — 설정·의존성·외부 서비스 진단
- [ ] README.md — 설치/설정/실행/트러블슈팅 4절
- [ ] hermes-memory-doctor 정상 종료 = 배포 준비 완료
- [ ] pytest: CLI smoke + config.example 유효성

## 필수 의존성 (core)

pydantic>=2, pyyaml, structlog, APScheduler, jsonschema, filelock,
lightrag-hku (필수), notion-client (필수)

## Optional extras

- embedding-api: openai 등 원격 임베딩
- embedding-local: sentence-transformers, torch CPU
- dev: pytest, ruff, mypy

## doctor 진단 항목 (순차)

1. config.yaml 존재·파싱
2. vault root 접근
3. LightRAG 서버 응답 (127.0.0.1:9621/openapi.json)
4. 임베딩 백엔드 로드
5. Notion API 키 유효성
6. 메타문서 16종 존재

## 구현 포인트

- Console script: hermes-memory-doctor → hermes_memory.cli:doctor
- config: Pydantic Settings + 환경변수 자동 매핑
- Secret: env > openclaw.json > yaml
- Optional extras 미설치 시 doctor가 설치 안내

## 리포트 템플릿

[7절 — 00_CORE 규격]