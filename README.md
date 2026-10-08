# 기아 유럽 PBV·LCV 리뷰 수집 MVP

Python + Playwright로 **화면에 표시된 DOM 텍스트**를 읽는 소규모 수집기입니다. VS Code에서 열고 실행할 수 있습니다. 챗GPT 대화 종료 후 상시 동작을 가정하지 않으며, 반복 수집은 별도 서버/PC의 스케줄러가 단발 명령을 호출합니다.

## 현재 검증 범위

- 최초 저장소는 소스·커밋이 없는 빈 저장소였습니다. 기존 후보 파일/프로젝트 지침은 발견되지 않았습니다.
- 첨부 `reviews.csv`: UTF-8, 26개 컬럼, 11,523개 행. FURGOVW_FORUM 11,505개, SALINES_MFOROS 18개이며 스위스 자료가 아닙니다. 파일은 수정하거나 DB에 가져오지 않았습니다. **출력 컬럼 호환성만 참고**했습니다.
- 스위스 조사용 호스트 후보 `www.auto-treff.ch`는 **사이트 존재·스위스 분류·자동 수집 정책·DOM 모두 미확인**입니다. 2026-10-07 공개 루트 HEAD 요청은 네트워크 프록시 CONNECT 403으로 차단되었습니다. 이는 사이트 자체의 접근 거부나 정책 확인을 뜻하지 않습니다. 확정된 커뮤니티라고 주장하지 않습니다.
- `config/swiss.review.json`은 실행 가능한 실사이트 어댑터가 아닌 검토용 설정입니다. 정책 게이트가 브라우저/네트워크 실행 전에 `needs_review`로 종료합니다. 사이트 정책을 확인하지 못했으므로 실제 리뷰 수집은 **0개**입니다.
- `config/local.json` 및 HTML은 직접 만든 **합성 샘플**입니다. 실제 스위스 소유자 후기나 후보 데이터가 아닙니다. 동일한 Chromium DOM 추출기로 총 3개 고유 샘플을 검증합니다. 전부 `needs_review`이며 언어 `de`도 fixture에 명시된 값입니다.

## 설치 및 실행

저장소 루트에서 Python 3.12 이상으로 실행합니다. 기존 checkout을 사용하세요. 별도 Git worktree를 만들 필요가 없습니다.

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell에서는 .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m playwright install chromium
python -m pbv_collector --config config/local.json
python -m unittest discover -s tests -v
```

Chromium/Chrome이 이미 설치되어 있으면 재다운로드할 필요 없이 사용합니다. 탐색 순서는 `PBV_BROWSER_EXECUTABLE` 환경 변수 → PATH의 `chromium`/`google-chrome` → Playwright Chromium입니다. 이 클라우드에서는 설치된 Chromium 151을 사용했습니다. Playwright 다운로드는 프록시 정책으로 차단되었고 TLS/체크섬 검증을 끄지 않았습니다. Windows에는 보통 Playwright Chromium을 설치하거나 `PBV_BROWSER_EXECUTABLE`에 로컬 Chrome 실행 파일의 경로를 지정합니다. Linux에서 공유 라이브러리가 부족하면 관리자가 공식 Playwright 안내에 따라 OS 의존성을 설치해야 합니다.

VS Code에서 Python 확장의 인터프리터로 `.venv`를 선택하면 제공된 `PBV local sample` 디버그 설정으로 실행할 수 있습니다.

```bash
# 진행 중 작업 재개 (동일 명령)
python -m pbv_collector --config config/local.json
# 완료된 큐를 새 회차로 재방문; 기존 ID 중복 방지 + 회차 대기시간 유지
python -m pbv_collector --config config/local.json --new-cycle
# 검토용 실사이트 설정: 요청 0건, needs_review, 종료 코드 2
python -m pbv_collector --config config/swiss.review.json
```

첫 로컬 실행은 3개를 저장합니다. 동일 DB로 다시 실행할 때는 신규 저장 0개가 정상입니다. 새 샘플 실험은 다른 `job_id`와 다른 DB 경로를 사용하는 것이 좋습니다. 원본 데이터는 지우지 마세요.

## 설정

`config/local.json`의 구조를 참고하세요. 상대 경로는 **저장소 루트 기준**입니다.

| 설정 | 의미 |
|---|---|
| `job_id`, `storage.database` | 작업 ID와 SQLite 파일. 작업별 독립 DB를 권장합니다. DB 옆 OS lock 파일로 CLI 동시 실행을 막습니다. |
| `mode` | `fixture` / `live`. fixture는 외부 요청을 차단하고 UTF-8 HTML을 브라우저에 로드합니다. |
| `host`, `seed_urls` | 승인된 HTTPS 호스트 하나와 공개 검색 결과/스레드 URL 목록. 다른 호스트 이동·로그인·비표준 포트는 차단합니다. |
| `allowed_path_prefixes` | live 모드에 필수인 승인된 공개 경로 목록. 예: `/forum/`. 빈 목록은 검토 상태로 중지합니다. robots.txt는 이 목록 밖에서 별도 정책 조회합니다. |
| `search.keywords`, `from`, `to` | 본문/제목 로컬 키워드 필터와 ISO 날짜 범위. 작성일이 불명이면 검수 보류로 보존합니다. |
| `vehicles` | 본문에 실제 나타난 문자열만 근거와 함께 차량 후보로 기록합니다. 소유/실사용 판정은 하지 않습니다. |
| `selectors` | ready, record, body, title, permalink, time, author, reactions, next, empty, access_barriers. 사이트별 실제 구조로 교체해야 합니다. |
| `limits` | 회차 신규 저장 수 / 페이지 접근 수 / 시간 / 일일 신규 저장 수 / 페이지 간격 / 재시도 횟수와 대기시간. |
| `schedule` | IANA 시간대, HH:MM 실행 창, 최소 회차 간격. start=end는 하루 전체 허용. 기본 Europe/Zurich, 30분 간격. |
| `market_evidence` | 커뮤니티의 스위스 범위를 확인한 근거. 작성자 국적 근거로 사용하지 않습니다. |
| `policy` | automation_allowed, terms_url, reviewed_at, review_note, selectors_verified. boolean을 켜는 것만으로 허가가 생기지 않습니다. 실제 검토 결과를 기록해야 합니다. |
| `storage.legacy_columns`, `common_columns` | 선택 사항: 각 CSV의 기존 필드 목록 중 선택·순서 지정. 기본은 전체 컬럼. JSONL은 항상 공통 전체 스키마. |

네트워크 호출은 문서 요청에 제한하고 이미지/스크립트/분석 요청을 차단합니다. robots.txt는 별도로 조회하며 문서 접근·네트워크 요청에 포함합니다. robots의 차단을 따르고 Crawl-delay와 설정 간격 중 큰 값을 사용합니다. robots 조회 실패는 검토 상태로 멈춥니다. robots 허용이 이용약관의 자동 수집 허용을 대체하지는 않습니다. JavaScript API나 더보기 버튼이 필요한 사이트는 이번 어댑터의 범위 밖입니다. `DOMAdapter.extract` 인터페이스(레코드 목록, 다음 URL 목록)를 유지하면서 사이트별 구현과 검증을 추가해야 합니다. 첫 구현은 미리 설정한 공개 검색 URL/스레드와 next 링크만 처리하며 검색 UI 입력이나 더보기 클릭은 구현하지 않았습니다.

현재 ID 매핑은 합성 DOM의 `data-post-id`, `data-comment-id`, `data-parent-post-id`, `data-parent-comment-id`를 읽습니다. 실사이트의 URL/ID 구조에 맞춘 별도 어댑터가 필요합니다. 메타데이터는 visible 요소의 텍스트/속성을 읽습니다. 언어는 해당 record의 명시적 `lang`, 시각은 화면 time 요소의 timezone 포함 datetime에만 의존합니다. 없는 필드는 빈 문자열입니다. ISO가 아닌 로컬 날짜 문자열은 raw_payload에 보존합니다.

## 저장 데이터와 상태

`data/local/` (실사이트 예시는 `data/swiss/`) 아래:

- `reviews.csv`: 첨부 파일과 **동일한 26개 컬럼 순서**. 없는 board/license/rating 값은 빈 값입니다. 전체 공통 레코드는 raw_payload JSON에도 보존합니다. 원본 CSV에서 상속한 라이선스는 없습니다.
- `common.csv`, `reviews.jsonl`: 공통 스키마 전체. CSV는 UTF-8 BOM, JSONL은 UTF-8. Unicode 독일어·한글 원문을 번역하거나 ASCII로 치환하지 않습니다.
- SQLite: records 테이블의 고유 source+post/comment ID (없으면 정규화 URL), jobs 테이블의 검색 조건·큐·처리 URL·커서·누적 저장 수·에러·next_allowed_at. OS 강제 종료 후에도 각 레코드 commit은 남고, 같은 페이지 재방문/ID 중복 제거로 이어갑니다. 페이지 번호만 재개 키로 사용하지 않습니다.

| 공통 필드 | 의미 |
|---|---|
| source_name / source_url | 사이트와 실제 레코드 permalink (필수) |
| external_post_id / external_comment_id / parent_post_id / parent_comment_id | 출처 ID 및 부모 관계; 없는 값은 빈 값 |
| title / review_text / author_id | 화면에 표시된 제목·본문·공개 작성자 식별자 |
| posted_at / collected_at | 확정 가능한 timezone 포함 작성 시각 / UTC 수집 시각 |
| target_vehicle / vehicle_match_evidence | 명시된 차량 문자열과 분류 근거 |
| language / target_market_code / market_evidence | 명시된 언어 및 커뮤니티 국가 근거. 작성자 국적을 확정하지 않음 |
| rating_or_reactions | 사이트가 표시한 원문 값; 별점 추정 없음 |
| collection_status / data_type | 기본 needs_review / unclassified. 문의·비교·시승·실사용 구분은 별도 검수 필요 |
| translated_text / summary / analysis | 원문과 분리한 후속 처리 필드. 현재 빈 값 |
| raw_payload | 원문 작성일 표시, 페이지 URL, 합성 여부와 범위 설명 |

필수 필드는 source_name, source_url, review_text, collected_at이며 출처 HTTPS, 차량/국가 근거를 검증합니다. 필수 항목 누락이나 Unicode replacement character(U+FFFD) 발견은 작업을 needs_review로 중지합니다. 다른 인코딩으로 잘못 디코딩된 모든 깨짐을 자동 판별·복구하는 기능은 아닙니다. 이미 손상된 원문은 원본 페이지와 대조해야 합니다.

작업 state: queued → running → completed / paused / needs_review / failed. 레코드의 collection_status와 작업 state는 별개입니다. 모든 수집 레코드는 아직 사람 검수를 통과한 분석 데이터가 아닙니다. 제한 종료는 paused, 접근 거부·CAPTCHA·구조 변경은 needs_review, 반복 네트워크/429 실패는 failed입니다. 429는 Retry-After 초/HTTP 날짜를 따르고 최소 회차 간격보다 짧게 재시도하지 않습니다. 처리 큐는 유지합니다. --scheduled는 needs_review/failed 작업을 자동으로 재시작하지 않습니다. 수정 후 수동 재검토가 필요합니다. 검색/사이트/정책/파싱 조건을 바꾸면 새 job_id를 요구하며 실행 제한·저장 경로·스케줄만 변경하는 재개는 허용됩니다.

로그 `last_run`: search_candidates는 파싱한 레코드 후보 수(재방문 중복 포함), pages_checked는 구조를 검사한 페이지 수, page_accesses는 문서 접근 시도 수(robots 포함), network_requests는 허용된 HTTP 요청 시도 수(실패 포함), saved_records는 이번 회차 신규 저장 수, duplicate_records는 DB 중복 수, review_pending은 신규 저장 중 검수 보류 수입니다. 실제 전송된 TCP 패킷 수나 UI 검색 결과 총수를 주장하지 않습니다. fixture page_accesses는 로컬 렌더 횟수이며 network_requests=0입니다.

## 반복 수집: 별도 서버의 스케줄러

아래는 **정책과 사이트 어댑터 검증을 마친 뒤** 활성화하는 예시입니다. 아직 실사이트용으로 등록/실행하지 않았습니다. PC/서버가 켜져 있어야 하고 VS Code나 채팅이 스케줄러 역할을 하지 않습니다.

Linux cron 예시(절대 경로를 실제 위치로 교체):

```cron
*/5 * * * * cd /srv/kia_crawling && /srv/kia_crawling/.venv/bin/python -m pbv_collector --config config/swiss.review.json --scheduled >> /srv/kia_crawling/data/scheduler.log 2>&1
```

5분마다 실행 여부를 확인하되 설정의 30분 간격·실행 창·Retry-After·일일 한도를 따릅니다. completed 작업은 다음 회차에 seed부터 재방문하므로 기존 스레드의 새 댓글도 다시 확인합니다. 신규 스레드는 seed 검색 결과에서 next 링크로 발견되는 범위에 제한됩니다. 이 MVP는 모든 포럼의 전체 발견/삭제/편집 이력을 보장하지 않습니다. 저장한 ID의 원문이 나중에 수정되면 기존 값은 덮어쓰지 않습니다.

Windows 작업 스케줄러 예시: 프로그램 `C:\path\kia_crawling\.venv\Scripts\python.exe`, 인수 `-m pbv_collector --config config/swiss.review.json --scheduled`, 시작 위치 `C:\path\kia_crawling`. 5분 반복, 새 인스턴스 시작 안 함으로 설정하세요. OS 재부팅 시 스케줄러 시작 설정도 별도로 필요합니다.

CLI 종료 코드: 0 정상/예정된 일시 중지, 2 검토 필요/실패, 3 이미 실행 중. 출력 JSON과 DB state를 함께 확인하세요.

## 사이트 활성화 전에 필요한 확인

1. 실제 스위스 공개 커뮤니티 하나를 확정하고 스위스 범위의 출처를 기록합니다. 현재 후보 호스트가 적합하지 않으면 대체합니다.
2. 운영자의 자동 수집·데이터 이용 조건, 개인정보·저작권 조건과 robots.txt를 검토합니다. 불명확하면 실행하지 않습니다. 허용된 URL 경로만 seed/탐색 규칙에 포함합니다.
3. 승인된 환경에서 소량의 공개 HTML/DOM을 확인하고 실제 게시글·댓글 ID, permalink, 본문·날짜·페이지 이동 규칙을 별도 어댑터로 구현합니다. 접근 제한을 우회하지 않습니다.
4. 낮은 제한값으로 소량 수집하고 원문/시간/관계/출처를 사람이 대조한 뒤 별도 서버 예약을 활성화합니다.

## 테스트

`python -m unittest discover -s tests -v`는 실제 Chromium으로 합성 HTML의 schema, 원문 Unicode 및 hidden 텍스트 제외, CSV 호환, 중복 댓글, 중간 레코드/페이지 제한 후 재개, 일일 한도, CAPTCHA/구조 변경 중지, 정책 게이트 요청 0건, HTTP 접근 상태/Retry-After를 검증합니다. 실사이트 통신 성공이나 실사이트 selector 적합성 테스트는 아닙니다.
