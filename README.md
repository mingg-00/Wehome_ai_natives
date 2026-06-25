# wehome-integration

통합 실행 레포입니다.

이 레포는 3개 에이전트의 소스를 복사하지 않고, 아래만 유지합니다.

- `docs/contract.md`
- `docs/developer_handoff.md`
- `orchestrator/` 코드
- `scripts/` 실행 및 배포 스크립트
- `env.example`

## 구조

```text
wehome-integration/
  orchestrator/
  docs/
  config/
  scripts/
  output/
  README.md
  env.example
```

## 사용 방식

1. 각 에이전트는 각자 자기 repo/branch를 유지합니다.
2. 이 통합 레포는 CLI 또는 HTTP로 에이전트를 호출합니다.
3. 내일 시연 기준으로는 CLI 호출이 가장 단순합니다.

## 시작

```powershell
copy env.example .env
.\scripts\run.ps1
```

