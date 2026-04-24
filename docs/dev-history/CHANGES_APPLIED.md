# CHANGES_APPLIED

| 대상 | 변경 내용 |
| --- | --- |
| `/root/obsidian/Remy's brain/Remy's brain/system` | `_system/` 으로 리네임 |
| `~/.hermes/config.yaml` | `vault.root`, `embedding.backend`, `lightrag.endpoint` 설정 추가 |
| `docs/codex-bundle/00_CORE.md` | P14 배포 가능성 원칙 + RECON 확정 사항 섹션 추가 |
| `docs/codex-bundle/P4_BACKENDS.md` | 목표/수용 기준을 LightRAG 필수·notion-client·pluggable embedding 기준으로 갱신 |
| `docs/codex-bundle/P11_HOOKS.md` | 공통 hook signature(flat kwargs) 수용 기준 추가 |
| `docs/codex-bundle/P1_META_A.md` | vault root 실측값 반영 요구 추가 |
| `docs/codex-bundle/P14_DEPLOY.md` | 신규 Phase 14 배포 문서 생성 |
| `vault_meta/_system/notion_datasource_map.md`, `docs/codex-bundle/P1_META_A.md`, `docs/QUESTIONS.md` | GDrive 파일 DB를 Phase 1 Notion 동기화 범위에서 제외(out-of-scope: 외부 파일 카탈로그)하고 관련 수용 기준/질문 상태를 정정 |

## 2026-04-23 아키텍처 정정 — knowledge/inbox only
- 실제 볼트 조사 결과: `_system/` 디렉터리가 존재했고, 내부 유의미 기존 파일 60개를 확인했다.
- 실제 볼트 적용: `_system/` 파일 60개를 `vault_meta/_system_backup/` 아래에 구조 보존 백업 후 live vault `_system/` 디렉터리를 삭제했다.
- 실제 볼트 적용: `knowledge/`, `inbox/` 디렉터리는 이미 존재하여 유지했다.
- 문서 정정: `vault_meta/_system/vault_spec.md`에서 볼트 note area를 `knowledge`, `inbox`만 허용하도록 수정하고, quarantine 경로를 `<vault_root>/_quarantine/YYYY-MM/`로 반영했다.
- 문서 정정: `vault_meta/_system/` 하위 메타문서와 `docs/codex-bundle/00_CORE.md`에서 `_system/`을 live vault 내부 구조가 아니라 Hermes 에이전트 시스템 config 번들 관점으로 정정했다.
- Q13 추가 없음: quarantine 경로는 기본안인 `<vault_root>/_quarantine/YYYY-MM/`를 채택했다.

### 실제 볼트 `_system/` 기존 유의미 파일 목록
- `_system/behavior/gdrive_ops.md`
- `_system/behavior/notion_ops.md`
- `_system/behavior/schedule_ops.md`
- `_system/behavior/tool_strategy.md`
- `_system/behavior/vault_behavior_rules.md`
- `_system/behavior/vault_ops.md`
- `_system/data_ops/dedup_check.md`
- `_system/data_ops/embedding_strategy.md`
- `_system/data_ops/query_strategy.md`
- `_system/data_ops/save_conversation.md`
- `_system/data_ops/save_gdrive.md`
- `_system/data_ops/save_notion.md`
- `_system/data_ops/tag_management.md`
- `_system/data_ops/vault_spec.md`
- `_system/evaluation/context_loading_eval.md`
- `_system/evaluation/conversation_save_eval.md`
- `_system/evaluation/deliverable_creation_eval.md`
- `_system/evaluation/full_sync_eval.md`
- `_system/evaluation/gdrive_sync_eval.md`
- `_system/evaluation/inbox_processing_eval.md`
- `_system/evaluation/knowledge_recall_eval.md`
- `_system/evaluation/notion_sync_eval.md`
- `_system/evaluation/prompt_proposal_eval.md`
- `_system/evaluation/schedule_management_eval.md`
- `_system/evaluation/self_audit_eval.md`
- `_system/evaluation/system_proposal_eval.md`
- `_system/evaluation/tag_proposal_eval.md`
- `_system/evaluation/tool_proposal_eval.md`
- `_system/evaluation/workflow_proposal_eval.md`
- `_system/neuro_genesis/apply_changes.md`
- `_system/neuro_genesis/autonomy_policy.md`
- `_system/neuro_genesis/evaluate.md`
- `_system/neuro_genesis/evaluation_protocol.md`
- `_system/neuro_genesis/optimization_cycle.md`
- `_system/neuro_genesis/prompt_proposal.md`
- `_system/neuro_genesis/tag_proposal.md`
- `_system/neuro_genesis/tool_proposal.md`
- `_system/neuro_genesis/workflow_proposal.md`
- `_system/self_reference/TAGS.md`
- `_system/self_reference/context_loading.md`
- `_system/self_reference/conversation_save.md`
- `_system/self_reference/deliverable_creation.md`
- `_system/self_reference/env.md`
- `_system/self_reference/feedback_collection.md`
- `_system/self_reference/full_sync.md`
- `_system/self_reference/gdrive_sync.md`
- `_system/self_reference/inbox_processing.md`
- `_system/self_reference/knowledge_recall.md`
- `_system/self_reference/notion_sync.md`
- `_system/self_reference/overview.md`
- `_system/self_reference/personal_calibration.md`
- `_system/self_reference/personalization.md`
- `_system/self_reference/routing_map.md`
- `_system/self_reference/schedule_management.md`
- `_system/self_reference/self_audit.md`
- `_system/self_reference/system_proposal.md`
- `_system/sync_pipeline/completed_task_sync.md`
- `_system/sync_pipeline/live_update.md`
- `_system/sync_pipeline/routing_rules.md`
- `_system/sync_pipeline/vdr_image_sync.md`
