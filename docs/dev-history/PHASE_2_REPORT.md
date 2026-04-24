# PHASE_2_REPORT

## 1. 변경 파일 목록
| 상대경로 | 상태 | 라인 증감 |
| --- | --- | --- |
| `vault_meta/_system/data_ops/file_policy.md` | 신규 | `+102` |
| `vault_meta/_system/data_ops/retention.md` | 신규 | `+68` |
| `vault_meta/_system/data_ops/binary_policy.md` | 신규 | `+59` |
| `vault_meta/_system/self_reference/persist_policy.md` | 신규 | `+60` |
| `vault_meta/_system/self_reference/scope_policy.md` | 신규 | `+51` |
| `vault_meta/_system/self_reference/hook_registry.md` | 신규 | `+68` |
| `vault_meta/_system/self_reference/quarantine_policy.md` | 신규 | `+51` |
| `vault_meta/_system/skills/skill_spec.md` | 신규 | `+59` |
| `vault_meta/_system/skills/skill_registry.md` | 신규 | `+62` |
| `vault_meta/_system/skills/default/session_close.md` | 신규 | `+30` |
| `vault_meta/_system/skills/default/notion_sync.md` | 신규 | `+30` |
| `vault_meta/_system/skills/default/quarantine_sweep.md` | 신규 | `+30` |
| `vault_meta/_system/skills/default/persist_attach.md` | 신규 | `+30` |
| `vault_meta/_system/E_config/model_limits.yaml` | 신규 | `+43` |
| `docs/QUESTIONS.md` | 갱신 | `+12` |
| `docs/PHASE_2_REPORT.md` | 신규 | `+59` |

## 2. 테스트 결과
- 실행 명령: 없음
- 결과: metadata-only Phase이며 사용자 지시가 `코드 작성 금지`, `실제 볼트 직접 쓰기 금지`, `Phase 3 이후 착수 금지`였으므로 테스트·정적분석은 수행하지 않았다
- 통과/실패 카운트: `0 / 0`

## 3. Acceptance 체크
| 항목 | 충족 근거 |
| --- | --- |
| B data_ops 3종 작성 | `vault_meta/_system/data_ops/` 아래 `file_policy.md`, `retention.md`, `binary_policy.md`를 생성했고, `file_type` registry·attachment path·hash-only retention을 [[vault_spec]] 규칙과 연결했다 |
| C self_reference 4종 작성 | `persist_policy.md`, `scope_policy.md`, `hook_registry.md`, `quarantine_policy.md`를 생성했고, `persist.process`/`persist.attach` 분기, scope=skill β 정책, 자동훅 3종, invariant 격리 규칙을 명시했다 |
| D skills 6종 작성 | `skill_spec.md`, `skill_registry.md`, `skills/default/` 4개 초안을 생성했고, hook↔skill binding과 `references/` 규약을 정리했다 |
| `E_config/model_limits.yaml` 작성 | `/root/.hermes/config.yaml`의 active model(`openai-codex/gpt-5.4`)과 `/root/.openclaw/agents/main/agent/models.json`의 numeric limits를 근거로 `context_window=272000`, `max_output_tokens=128000`을 기록했다 |
| Phase 1 SSoT 일관성 유지 | `vault_spec.md`, `TAGS.md`, `notion_datasource_map.md`는 수정하지 않았고, 새 문서에서 `area=knowledge`, type enum 7종, tag exact-match 원칙만 참조했다 |
| 실제 볼트 비수정 | 모든 산출물을 작업 루트 내부(`vault_meta/_system/`, `docs/`)에만 작성했고 `/root/obsidian/...`에는 쓰지 않았다 |
| Q10 처리 | `TAGS.md`와 `notion_datasource_map.md`의 existing exact-match 규칙을 근거로 `docs/QUESTIONS.md` Q10을 Resolved 처리했다 |

## 4. RECON.md 보강 사항
- `/root/.hermes/config.yaml` 실측 결과 현재 runtime에는 `vault.root: "/root/obsidian/Remy's brain/Remy's brain"`가 존재한다. Phase 0 시점 기록과 달라졌거나 이후 config가 보강된 상태다
- `/root/.openclaw/agents/main/agent/models.json`의 `codex.models[gpt-5.4]`, `codex.models[gpt-5.3-codex-spark]`에서 numeric context/output limit을 확인했다
- 실측 `~/.hermes/skills/`는 `SKILL.md`를 가진 skill 24개를 보유하고, optional subdir는 `references/ 7`, `assets/ 4`, `scripts/ 4`, `templates/ 4`, `rules/ 1`로 관찰됐다
- 실측 vault markdown frontmatter의 `file_type` 값은 모두 `md`였고, `attachments/` 하위 실파일은 이번 관찰 시점에 없었다
- `P9_SEARCH.md`의 `frontmatter quarantine: true` 문구는 Phase 1의 닫힌 9필드 schema와 충돌하므로, Phase 2는 경로 기반 quarantine을 우선 채택하고 질문으로 승격했다

## 5. 질문 보류 신규 항목
- Q11 `Quarantine flag vs frontmatter 9-field closed schema` 추가
- Q12 `Default skill draft basenames for skills/default/*.md` 추가
- Q7 `LLM token limits`를 Resolved 처리
- Q10 `Project relation → TAGS registry crosswalk`를 Resolved 처리

## 6. 다음 Phase 선행조건
- Phase 3 이후 코드는 본 Phase 문서를 SSoT로 읽도록 구현하면 된다
- 다만 `skills/default/*.md` canonical basename이 다르다면 Phase 5 meta_loader 진입 전 Q12 확인이 필요하다
- 검색 레이어에서 `quarantine` 상태를 frontmatter로 볼지 경로로 볼지 Q11 결정이 Phase 9 전에 필요하다
- 그 외 Phase 1/2 SSoT 범위를 넘는 enum 확장은 여전히 금지다

## 7. 간략한 회고
이번 Phase는 정책 문서만으로도 이후 파이프라인 분기 조건을 거의 고정할 수 있게 만드는 작업이었다. 특히 `persist.process`/`persist.attach`, `scope=skill`, hook 3종, binary 보존, model limit 근거를 서로 교차 참조로 묶어 두어 코드 단계의 하드코딩 여지를 줄였다. 다만 기본 스킬 4종의 basename SSoT와 quarantine flag 표기 방식은 bundled sources만으로 확정되지 않아, 추측 대신 provisional draft + QUESTIONS 승격으로 정리했다.
