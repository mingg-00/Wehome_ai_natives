#!/bin/bash
# Wehome 봇 macOS launchd 등록 스크립트
set -e

PROJECT_DIR="/Users/gimminji/현장실습/wehome-marketing-engine"
PLIST_SRC="$PROJECT_DIR/deploy/me.wehome.bot.plist"
PLIST_DST="$HOME/Library/LaunchAgents/me.wehome.bot.plist"

# 로그 디렉토리 생성
mkdir -p "$PROJECT_DIR/logs"

# 기존 서비스 있으면 먼저 언로드
if launchctl list | grep -q "me.wehome.bot"; then
    echo "기존 서비스 언로드 중..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# plist 복사 및 등록
cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"

echo "✅ 봇 서비스 등록 완료"
echo ""
echo "명령어:"
echo "  상태 확인 : launchctl list | grep wehome"
echo "  로그 보기  : tail -f $PROJECT_DIR/logs/bot.log"
echo "  에러 로그  : tail -f $PROJECT_DIR/logs/bot.error.log"
echo "  중지       : launchctl unload $PLIST_DST"
echo "  재시작     : launchctl unload $PLIST_DST && launchctl load $PLIST_DST"
