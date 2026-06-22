# SNS 연결 가이드 — 토큰 발급 → `.env` (한 번만 연결하면 이후 자동 게시)

> **개념:** 매번 로그인 창이 뜨는 게 아니라, **각 플랫폼에서 최초 1회 "앱 연결(로그인+권한 허용)"** 하면 **access token**(저장된 로그인 열쇠)이 나옵니다. 그 토큰을 `.env`에 넣으면 우리 에이전트가 그걸로 **자동 게시**(로그인 창 없음).
>
> **공통 주의:** ① 자사 **비즈니스/개발자 계정** 필요 ② 게시 권한은 보통 **앱 심사(App Review)** 통과해야 외부에 보임(본인 소유 계정은 개발/테스트 모드에서 먼저 가능) ③ IG·Pinterest는 **공개 이미지 URL**이 있어야 실게시(없으면 dry-run).

---

## 1. Meta — Instagram + Facebook + Threads
**준비:** Facebook 페이지 + Instagram을 **비즈니스/크리에이터 계정**으로 전환해 그 페이지에 연결.

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App**(유형: Business)
2. 제품 추가: **Facebook Login**, **Instagram Graph API**
3. 권한(스코프) 요청:
   - Facebook 게시: `pages_manage_posts`, `pages_read_engagement`
   - Instagram 게시: `instagram_basic`, `instagram_content_publish`
   - Threads 게시: `threads_basic`, `threads_content_publish`
4. **Graph API Explorer**에서 User Access Token 발급 → **장기 토큰(60일)**으로 교환
   ([Access Token Tool](https://developers.facebook.com/tools/accesstoken/) 또는 `oauth/access_token` 호출)
5. 필요한 ID 조회(Graph API Explorer):
   - 페이지 ID: `GET /me/accounts`
   - IG 비즈니스 계정 ID: `GET /{page-id}?fields=instagram_business_account`

**`.env` 매핑:**
```
META_ACCESS_TOKEN=<장기 User/Page 토큰>
FB_PAGE_ID=<페이지 ID>
IG_USER_ID=<인스타 비즈니스 계정 ID>
THREADS_USER_ID=<Threads 사용자 ID>
```
> ⚠️ **Threads는 별도 API**(`graph.threads.net`)라 보통 **Threads 전용 토큰**이 필요합니다. FB/IG와 다른 토큰을 쓸 수 있어, Threads가 안 되면 알려주세요 — 커넥터를 Threads 전용 토큰으로 분리해 드립니다.
> ⚠️ IG 실게시는 글에 **`image_url`(공개 이미지 주소)** 가 필요합니다.

---

## 2. X (Twitter)
1. [developer.x.com](https://developer.x.com) → **Project + App** 생성 (무료 티어는 쓰기 제한이 있을 수 있어 **Basic($) 이상** 권장)
2. App 설정에서 권한을 **Read and Write**로
3. App → *User authentication settings* → 권한을 **Read and Write**로
4. **OAuth 1.0a 정적 토큰(권장 · 만료 없음)** 발급: App → *Keys and tokens* 에서
   - **API Key / API Key Secret** (= Consumer key/secret)
   - **Access Token / Access Token Secret** (Read and Write 권한으로 생성)

**`.env` 매핑 (이 4개만 넣으면 끝 — 만료 없이 자동게시):**
```
X_API_KEY=<API Key>
X_API_SECRET=<API Key Secret>
X_ACCESS_TOKEN=<Access Token>
X_ACCESS_SECRET=<Access Token Secret>
```
> ✅ **커넥터가 OAuth 1.0a 서명 방식으로 안정화됨** — 위 4종이 있으면 우선 사용(만료 없음). 없고 `X_BEARER_TOKEN`(OAuth2 user)만 있으면 그걸로 대체(만료형).
> ⚠️ X API는 유료 티어가 필요할 수 있습니다(쓰기 권한/한도 확인).

---

## 3. Pinterest
1. [developers.pinterest.com](https://developers.pinterest.com) → 앱 생성 (Trial → 검수 후 Standard 승격 시 한도↑)
2. 스코프: `pins:write`, `boards:read`
3. OAuth 연결 → **access token** 발급
4. 보드 ID 조회: `GET https://api.pinterest.com/v5/boards`

**`.env` 매핑:**
```
PINTEREST_TOKEN=<access token>
PINTEREST_BOARD_ID=<보드 ID>
```
> ⚠️ 핀 실게시는 **`image_url`(공개 이미지 주소)** 가 필요합니다.

---

## 연결 후 확인
```bash
# 토큰 넣은 뒤
python main.py social-approve <id>     # 승인
python main.py social-publish          # dry-run → '게시 완료(id=...)'로 바뀌면 성공
```
- `dry-run — XXX 없음`이 뜨면 해당 토큰이 비어있는 것 → `.env` 확인
- `dry-run — 이미지 URL 필요`면 IG/Pinterest용 이미지 자산이 없는 것

## 다음 병목: 이미지
IG·Pinterest 실게시는 **공개 이미지 URL**이 필수입니다. → 다음 단계로 **이미지 자동 생성 + 호스팅**을 붙이면 IG/Pinterest까지 완전 자동화됩니다. (X·Facebook·Threads는 텍스트라 토큰만 있으면 바로 실게시)
