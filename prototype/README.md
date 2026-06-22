# prototype/ — MCP 커넥터 (보존용, 라이브 채널 아님)

> ⚠️ 이건 마케팅 엔진의 라이브 기능이 **아닙니다.** 일반 여행자가 직접 MCP 서버를
> 설치할 일은 없기 때문입니다. 여기 있는 코드는 **개념 증명 + 대표님 설득 자료**입니다.

## 왜 라이브에서 뺐나
- `mcp_server.py`는 **로컬(stdio) MCP 서버** → 개발자가 본인 Claude Desktop/Cursor에
  설치해야만 동작. **고객 도달 = 0.**
- 고객이 "설치 없이" 닿는 유일한 길 = **회사가 원격 MCP를 호스팅 → ChatGPT Apps /
  커넥터 디렉터리에 공식 등록.** 그러면 모든 ChatGPT 사용자가 토글 하나로 "Wehome"을
  켠다(설치 X). → 이건 **회사·BD가 추진할 일**이지 인턴이 지금 배포할 수 없다.

## 그래도 보존하는 이유 (이게 핵심 자산)
측정된 증명: **AI에 위홈을 도구로 쥐여주면 Share of AI Voice가 0% → 100%로 상승**
(`python main.py monitor --with-tools`). 즉, **회사가 위홈 커넥터를 ChatGPT Apps에
올리면 AI가 한국 숙소 질문에 위홈을 추천하기 시작한다**는 근거다. 대표님께 "원격 MCP
커넥터에 투자하자"를 설득하는 데이터.

## 실제 제품화 경로 (회사가 할 일)
1. `engine/wehome_tools.py`의 도구 로직을 실제 위홈 예약 API에 연결
2. 원격 MCP(HTTP/SSE) 서버로 호스팅
3. **ChatGPT Apps / 커넥터 디렉터리에 공식 제출** → 전 사용자 노출(무설치)

## 파일
- `mcp_server.py` — FastMCP 로컬 서버(데모용). `pip install mcp` 후 `python prototype/mcp_server.py`
- `claude_desktop_config.snippet.json` — (구) 로컬 등록 스니펫. 데모/개발 시에만.

도구 로직 자체(`engine/wehome_tools.py`)는 엔진에 남아 있고, SoAV 증명(`monitor --with-tools`)이 이를 사용한다.
