# wehome-integration

Discord 명령으로 `video-agent -> sns-upload-agent -> analytics-agent` 파이프라인을 실행하는 통합 레포입니다.

이 레포의 기준은 다음입니다.

- 에이전트 소스는 복사하지 않는다
- orchestrator는 실행 순서와 결과 저장만 담당한다
- Discord Bot은 `/run_campaign` 명령을 노출한다
- Python import 우선, 실패 시 subprocess fallback
- HTTP 서버 방식은 사용하지 않는다

## 프로젝트 구조

```text
wehome-integration/
  agents/
  config/
  discord_bot/
  docker/
  docs/
  orchestrator/
  runtime/
  data/
  shared/
  docker-compose.yml
  railway.toml
  requirements.txt
  .env.example
```

## 최종 동작 흐름

```text
Discord User
→ Discord Bot
→ Orchestrator
→ Video Agent
→ SNS Upload Agent
→ Analytics Agent
→ summary.json 생성
→ Discord Embed 전송
```

## 환경변수 설정

`.env.example`을 `.env`로 복사한 뒤 채웁니다.

필수 값:

```env
DISCORD_TOKEN=
INSTAGRAM_ACCESS_TOKEN=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
CONTRACT_VERSION=
```

선택 값:

```env
ORCHESTRATOR_MODE=direct
DATA_DIR=data
RUNTIME_DIR=runtime
JOB_POLL_INTERVAL_SECONDS=2.0
DISCORD_GUILD_ID=
VIDEO_AGENT_IMPORT=
VIDEO_AGENT_FUNCTION=
VIDEO_AGENT_CMD=
SNS_AGENT_IMPORT=
SNS_AGENT_FUNCTION=
SNS_AGENT_CMD=
ANALYTICS_AGENT_IMPORT=
ANALYTICS_AGENT_FUNCTION=
ANALYTICS_AGENT_CMD=
```

## Agent 연결 방식

우선순위는 다음과 같습니다.

1. Python import 방식
2. subprocess 방식

각 에이전트는 아래 형태로 연결합니다.

```python
result_video = run_video_agent(context)
result_sns = run_sns_agent(result_video, context)
result_analytics = run_analytics_agent(result_sns, context)
```

`VIDEO_AGENT_IMPORT`, `SNS_AGENT_IMPORT`, `ANALYTICS_AGENT_IMPORT`에 실제 모듈 경로를 넣으면 import 방식으로 실행됩니다.  
모듈 경로를 못 찾으면 `*_CMD`에 정의된 subprocess 명령으로 fallback 합니다.

## 로컬 실행

1. 의존성 설치

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 환경변수 준비

```powershell
Copy-Item .env.example .env
```

3. Discord Bot 실행

```powershell
python -m discord_bot.main
```

4. Orchestrator 단독 실행 확인

```powershell
python -m orchestrator.main --run-once
```

## Docker 실행

전체 스택 실행:

```powershell
docker compose up --build
```

서비스:

- `discord-bot`
- `orchestrator`

기본적으로 Bot은 `ORCHESTRATOR_MODE=direct`로 import 실행을 사용합니다.  
`orchestrator` 서비스는 worker 모드로 함께 띄워 둘 수 있습니다.

## Railway 배포

현재 `railway.toml`은 Discord Bot 배포 기준으로 맞춰져 있습니다.

배포 절차:

1. Railway에 이 repo를 연결한다.
2. `DISCORD_TOKEN` 등 환경변수를 Railway Variables에 등록한다.
3. Start command는 `python -m discord_bot.main`을 사용한다.
4. Discord Bot 서비스는 `always` 재시작 정책으로 둔다.

필요하면 orchestrator를 별도 Railway 서비스로 분리해 같은 이미지를 `python -m orchestrator.main --worker`로 실행할 수 있다.

## 결과 저장

실행 결과는 `data/` 아래에 저장한다.

```text
data/
├── video_result.json
├── sns_result.json
├── analytics_result.json
└── summary.json
```

## 유지보수 원칙

- 에이전트 코드는 통합 레포에 복사하지 않는다
- 에이전트 인터페이스가 바뀌면 `agents/` 어댑터만 먼저 수정한다
- 계약이 바뀌면 `docs/contract.md`를 먼저 갱신한다
- 배포 전에 Docker와 Railway 설정을 함께 맞춘다

