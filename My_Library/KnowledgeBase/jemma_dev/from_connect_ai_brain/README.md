# Connect AI 로컬 뇌 (이전 `.connect-ai-brain` 이관)

**이전 위치(레거시):** `C:\Users\user\.connect-ai-brain`  
**지금(팀 정리 후):** 이 폴더 — `D:\MONEY lol\My_Library\KnowledgeBase\jemma_dev\from_connect_ai_brain`

## 구조

| 항목 | 설명 |
|------|------|
| `00_Raw/` | Connect AI가 쓰던 **Raw** 트리 (이관 복사본) |
| `10_Wiki/` | Connect AI가 쓰던 **Wiki** 트리 (이관 복사본) |
| `.gitignore` | (가능 시) 이전 루트에서 복사 |

**My_Library 앱**의 `Wiki/`, `Raw_Materials/`와 **완전히 같지 않을 수 있음** — 이 트리는 **Connect AI 확장의 로컬 뇌**용이었다.  
잼마 **플레이북·한 줄 뇌**(`jemma_learned_log.md`)은 **이 폴더 밖** `..\` 에 있다.

## Cursor(Connect AI) 설정

- **Connect AI** 확장: **Local Brain** 경로를 **이 폴더**로 둔다.  
- 사용자 `settings.json` 키: `connectAiLab.localBrainPath`  
  - 값: `D:\MONEY lol\My_Library\KnowledgeBase\jemma_dev\from_connect_ai_brain` (JSON 이스케이프는 `\\`)
- **`connectAiLab.secondBrainRepo` (GitHub URL):** 로컬 폴더를 옮겼다고 **자동으로 바꿀 필요는 없음** — **같은 원격 `memoy1` 등**을 쓰면 **주소 그대로** 두면 된다. 바꾸는 경우는 **다른 깃허브 저장소**로 갈아탈 때뿐.
- **My_Library** 설정 화면의 **위키→뇌 동기화**(`POST /api/settings/sync-wiki-to-brain`)는 **`10_Wiki`로 복사**한 뒤, **이 루트에 `.git`이 있을 때만** `git push`한다. (이관 시 `.git`을 복사하지 않았다면 푸시는 생략·메시지 참고)

## 이전 `.git` 폴더

- 이전 `C:\Users\user\.connect-ai-brain\.git`은 **복사하지 않음**.  
- Git 이력이 필요하면 **옛 경로**에서 보관·삭제를 **직접** 결정한다.
