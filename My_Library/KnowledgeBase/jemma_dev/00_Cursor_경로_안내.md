# Cursor / `@` 로 `jemma_learned_log` 를 열 때 (찾을 수 없다고 할 때)

같은 파일이어도 **Cursor에서 연 폴더(워크스페이스 루트)** 가 다르면 **올바른 @ 경로가 달라진다.**

| 워크스페이스로 연 폴더 | 채팅에 `@` 로 걸 **상대 경로** |
|------------------------|----------------------------------|
| `D:\MONEY lol` (상위만 연 경우) | `My_Library/KnowledgeBase/jemma_dev/jemma_learned_log.md` |
| `D:\MONEY lol\My_Library` (앱 루트만 연 경우) | `KnowledgeBase/jemma_dev/jemma_learned_log.md` |

**팁:** 파일 탐색기에서 `jemma_learned_log.md` 를 **드래그**하거나, Cursor 왼쪽 트리에서 **우클릭 → Copy Path / @ 언급**에 넣는 방식이 가장 덜 틀린다.

**절대 경로(참고):**  
`D:\MONEY lol\My_Library\KnowledgeBase\jemma_dev\jemma_learned_log.md`

**`<read_brain>` 같은 태그**는 제품·프롬프트에 따라 **실제 파일을 안 열 수 있음** → **@파일** 또는 **본문에 절대 경로 붙여넣기**를 쓸 것.
