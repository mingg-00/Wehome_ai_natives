# 전략 정렬 — "AI WEHOME K-DO" 제안서 ↔ Marketing Engine

이 도구는 위홈 AI Native 전략 제안서의 **Content & Local Intelligence Cell(§15.8)**을
실제 코드로 구현한 것이다. 제안서의 멀티에이전트 구조(§2.3)·승인 체계(§2.6)·
거버넌스(§17.2)·KPI(§16)에 1:1로 정렬된다.

## 1) 멀티에이전트 매핑 (제안서 §2.3)

| 제안서 Agent | 이 도구의 구현 | 역할 |
|---|---|---|
| **Orchestrator Agent** (§2.3.1) | `main.py` (CLI) | 요청 분류·파이프라인 호출·결과 취합 |
| **SEO/SAIO Agent · Listing Rewrite Agent** (Specialist §2.3.3) | `engine/generator.py` | 주제→본문/FAQ/메타/schema 생성 |
| **Claim Review · Legal Risk Agent** (Governance §2.3.5) | `engine/governance.py` | §17.2 법적 표현 자동 검수 |
| **AI Visibility · Channel Performance Agent** | `engine/monitor.py` | AI가 위홈을 추천/인용하는지 측정 |
| **Brand & Slogan Governance** (§13.5) | `engine/brand.py` | 공식 슬로건·검증 사실·금지표현 |
| **Human Owner** (§2.3.6) | `approve` 게이트 | 발행 최종 승인(사람) |

## 2) 승인 권한 단계 (제안서 §2.6)

| Level | 정의 | 이 도구 |
|---|---|---|
| Level 1 | 초안 생성 | `generate` (자동) |
| Level 2 | Low-risk 자동 실행 | 검수 PASS/WARN 초안 저장 (자동) |
| **Level 3** | **Medium-risk 사람 승인 후 실행** | **`approve` = 발행 승인 (사람)** |
| Level 4 | High-risk 경영/법무 | 정부 허가 표현 변경·정책성 콘텐츠 (사람 별도 검토) |

→ 마케팅 문구는 법적 리스크(§17.2)가 있어 **Level 3**으로 고정. 100% 무인 발행 안 함.

## 3) KPI 정렬 (제안서 §16)

- **North Star (§16.0):** AI-assisted Booking Value — 이 도구는 그 상류(트래픽·AI 노출)를 만든다.
- **이 도구의 선행 KPI (§16.4):**
  - **Share of AI Voice (SoAV)** — AI가 한국 숙소 질문에 위홈을 추천/인용하는 비율
  - **AI 인용 가능 페이지 수** — 생성·승인된 GEO 콘텐츠 수
  - 브랜드/오가닉 검색 유입(연동 예정)

### 📊 측정된 SoAV (Share of AI Voice)
- **기준선 = 0%** (2026-06-16, gpt-4o, 중립 질문 10개): AI는 위홈을 한 번도 추천하지 않고 Airbnb·Booking·Agoda만 제시.
- **MCP 도구 장착 = 100%** (`monitor --with-tools`): AI에 위홈 MCP 도구를 쥐여주자 10/10 질문에서 위홈 추천(`search_wehome_stays`·`explain_legal_home_sharing_in_korea` 자동 호출), 경쟁사 언급도 급감.
- **결론: MCP 등록이 SoAV를 0%→100%로 끌어올린다는 것을 실측 증명.** 남은 일 = 실제 위홈 API 연동 + AI 클라이언트(ChatGPT/Claude)에 실제 등록.

## 4) 다음 develop 로드맵 (제안서 연결)

1. 🧪 **MCP / Open API** (§10.1–10.2) — **프로토타입**(`prototype/`): 로컬 설치형이라 고객 도달 0 → 라이브에서 제외. 고객 도달은 *회사가 원격 MCP 호스팅 → ChatGPT Apps 공식 등록*(무설치)이라야 가능 = 회사·BD 과제. 가치 증거(SoAV 0%→100%)는 `monitor --with-tools`로 엔진에 보존, 대표 설득 자료로 사용
2. **CMS 자동 발행** — `approve` 후 위홈 블로그 API로 게시
3. **리뷰 기반 콘텐츠** (§9.3) — 후기 요약을 콘텐츠·schema로
4. **숏폼/SNS 자동화** (§9.4) — 생성 글을 릴스/카드로 재가공
5. **현장 데이터(Local Intelligence) 연동** (§9.2) — 인턴 촬영/인터뷰 → 개인화 추천 근거
