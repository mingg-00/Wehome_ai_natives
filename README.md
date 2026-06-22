# Wehome AI Marketing Engine 🤖

위홈 트래픽 성장을 위한 **콘텐츠 자동 생성기**.
주제만 던지면(또는 백로그에서 스스로 골라) **영문 SEO+GEO 완성본**을 만들고,
**법적 가드레일을 자동 검수**한 뒤, **사람이 승인 버튼을 한 번** 누르면 발행 준비가 끝난다.

> 자동화 수준: **생성·검수 자동 + 사람 승인 후 발행** (마케팅 문구의 법적 리스크 때문에 100% 무인 발행은 일부러 막아둠 — 제안서 §17.2)

## 무엇을 자동으로 해주나

```
주제 → ① 본문/FAQ/메타 자동 생성(GEO 포맷) → ② JSON-LD schema 자동 조립
     → ③ 법적 가드레일 자동 검수 → ④ 초안 저장 →  [사람] approve → 발행
```

- **GEO/AEO 포맷 내장**: 질문형 헤딩 · 첫 문장 직답 · FAQ · 구조화 데이터 → ChatGPT·Perplexity·구글 AI 개요 인용 최적화
- **브랜드 일관성**: 공식 슬로건("Your home in Korea" 등)을 자동 적용
- **법적 안전장치(§17.2)**: "정부가 숙소를 인증/허가"로 읽힐 표현, 과장("guaranteed", "100% safe")을 자동 탐지해 **승인 차단**

## 설치

```bash
cd wehome-marketing-engine
pip install -r requirements.txt
cp .env.example .env      # OPENAI_API_KEY 입력 (없으면 오프라인 스켈레톤 모드)
```

> 키가 없어도 구조/스키마/검수 파이프라인은 그대로 시연된다. 실제 완성본 prose는 키 필요.
> 품질을 높이려면 `.env`에서 `OPENAI_CHAT_MODEL=gpt-4o` 권장.

## 사용법

```bash
python main.py list                 # 토픽 백로그(ICE順) + 생성 현황
python main.py generate --next      # ICE 최상위 미생성 토픽 1개 자동 생성
python main.py generate --auto 3    # 상위 3개 연속 생성
python main.py generate "Where to stay in Seoul"   # 특정 주제 (블로그)
python main.py generate "..." --format reddit       # Reddit 답변
python main.py generate "..." --format shortform    # 숏폼(Shorts/Reels/TikTok) 대본
python main.py generate "..." --format pinterest     # Pinterest 핀
python main.py generate "..." --format all           # 블로그+Reddit+숏폼+Pinterest 한번에
python main.py review  <slug>       # 검수 리포트 다시 보기
python main.py approve <slug>       # ✅ 사람 발행 승인 (게이트)
python main.py status               # 생성물 상태(DRAFT/APPROVED)
python main.py radar --auto 3       # 📡 Reddit 기회탐색 + 답변초안(사람이 게시)
python main.py monitor              # 📡 AI 노출(SoAV) 측정
python main.py monitor --with-tools # 📈 위홈을 AI 도구로 쥐여줬을 때 SoAV (프로토타입 증명)
python main.py dashboard            # 🖥 시각 대시보드(HTML 파일)
python main.py serve                # 🌐 대시보드 서버 — "🚀 지금 게시" 버튼 동작

# SNS 자동 포스팅 (자사 계정: Instagram/Threads/X/Pinterest/Facebook)
python main.py social-gen "<주제>" --source "<보도/스토리>"   # 생성→검수→예약큐
python main.py social-check                                  # 🔌 플랫폼 연결 상태 점검
python main.py social-queue                                  # 큐 보기
python main.py social-approve <id>                           # ✅ 승인
python main.py social-publish [--due]                        # 🚀 게시(실제/dry-run)
```

## SNS 자동 포스팅 에이전트 (자사 계정 전용)

위홈 **자사 브랜드 계정**에 플랫폼별 네이티브 문안을 생성→검수→예약→(승인)→자동 게시.
남의 커뮤니티 자동 게시·카르마 파밍은 하지 않음(그건 `radar`가 사람 게시).

- 토큰(.env)이 있으면 **실제 게시**, 없으면 **dry-run 미리보기**. IG/Pinterest는 이미지 URL 필요(없으면 dry-run).
- 예약 자동게시: cron으로 `social-publish --due`를 주기 실행 → 승인된 항목이 예약시간에 게시됨.
```bash
# 매시 정각, 승인되고 예약시간 도래한 SNS 글 자동 게시
0 * * * * cd /path/wehome-marketing-engine && python main.py social-publish --due
```

## Reddit 기회 레이더 (사람이 직접 게시)

`radar`는 **자동 게시하지 않습니다.** Reddit 약관상 자동 댓글/카르마 파밍은 금지(스팸·조작)이며 브랜드에 치명적이라 의도적으로 제외했습니다. 대신:
1. 공개 검색(읽기 전용)으로 최근 관련 스레드를 찾고
2. 각 스레드에 맞는 **진짜 도움되는 답변 초안**(위홈 미언급 기본 + 디스클로저 단 선택 위홈 한 줄)을 생성
3. 대시보드에서 검토 → 복사 → **본인이 직접 게시**

```bash
# Reddit 공식 API 권장: reddit.com/prefs/apps 에서 앱 생성 후 .env에 REDDIT_CLIENT_ID/SECRET
python main.py radar --auto 3
```
원칙: 순수 도움 답변 기본(9:1 규칙), 위홈 언급 시 디스클로저 필수(검수가 강제), 같은 문구 복붙 금지.

## MCP 커넥터 (제안서 §10) → `prototype/` 로 이동

일반 여행자가 직접 MCP 서버를 설치할 일은 없으므로 **라이브 기능에서 제외**했다.
고객이 무설치로 닿는 길은 *회사가 원격 MCP를 호스팅 → ChatGPT Apps에 공식 등록*뿐이며,
이는 회사·BD가 추진할 일이다. 개념 증명 코드와 설득 자료는 [prototype/](prototype/) 참고.

단, 그 가치의 **증거**는 엔진에 남겨뒀다: `python main.py monitor --with-tools` →
위홈을 AI 도구로 쥐여주면 **SoAV 0%→100%**. (도구 로직: `engine/wehome_tools.py`)

> 전략 정렬 상세는 [STRATEGY.md](STRATEGY.md) 참고.

생성물은 `output/<slug>/` 에 저장된다:
- `article.md` — CMS에 그대로 붙여넣을 게시용 완성본 (메타+본문+FAQ+schema)
- `faq_schema.json`, `article_schema.json` — JSON-LD
- `status.json` — 상태/검수 결과

## 매일/매주 자동으로 돌리기 (선택)

cron으로 주기 실행하면 "콘텐츠 공장"이 된다. 단, 발행은 여전히 사람 승인 후:

```bash
# 매주 월 09:00 ICE 상위 3개 초안 자동 생성 (검수까지) → 사람이 골라서 approve
0 9 * * 1 cd /path/wehome-marketing-engine && python main.py generate --auto 3
```

## 토픽 추가

`data/topics.json` 에 `{topic, primary_keyword, intent, ice}` 추가. ICE 높은 순으로 생성된다.

## 구조

```
engine/
  config.py      설정(OPENAI_API_KEY, 모델)
  brand.py       공식 슬로건·검증된 사실·법적 가드레일(금지표현)  ← 브랜드 두뇌
  llm.py         OpenAI 래퍼(JSON 강제)
  generator.py   주제→본문/FAQ/메타 생성 + schema 조립 + 게시용 마크다운 렌더
  governance.py  자동 검수(가드레일/포맷)
  publisher.py   초안 저장 + 발행 승인 게이트
main.py          CLI
data/topics.json 콘텐츠 백로그(ICE)
output/          생성물
```
