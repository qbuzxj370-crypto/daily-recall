"""환경설정 + 조정 가능한 상수. env는 .env에서 로드(없으면 OS env)."""
import os
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- 시크릿/외부 ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NOTION_API_KEY = os.environ.get("NOTION_API_KEY", "")
NOTION_DB_ID = os.environ.get("NOTION_DB_ID", "")
# Notion 2025-09 API는 data source 단위로 쿼리/생성. 미설정 시 DB에서 자동 해석(단일 소스 가정).
NOTION_DATA_SOURCE_ID = os.environ.get("NOTION_DATA_SOURCE_ID", "")

# Slack Incoming Webhook(선택). 미설정 시 슬랙 질문 push 자동 비활성.
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

# --- 모델 (현행, 2026-06 기준) ---
MODEL = os.environ.get("DR_MODEL", "claude-sonnet-4-6")
# 폴백 모델: 기본 모델이 API 오류/검증 실패로 막히면 승계(동일 Anthropic, 추상화 없음).
# 가용성↑·저비용 티어로 회복탄력성 확보. 기본 모델과 같으면 폴백 비활성.
MODEL_FALLBACK = os.environ.get("DR_MODEL_FALLBACK", "claude-haiku-4-5")
MAX_TOKENS = 2000

# --- 타임존 (KST 하드코딩; cron은 UTC로 환산해 0 22 * * *) ---
TIMEZONE = ZoneInfo("Asia/Seoul")

# --- 난이도 가중 랜덤: 카테고리 누적 출제수 -> 난이도별 확률 ---
def difficulty_weights(count: int) -> dict[str, float]:
    if count <= 2:
        return {"기초": 0.7, "중급": 0.3, "심화": 0.0}
    if count <= 6:
        return {"기초": 0.2, "중급": 0.6, "심화": 0.2}
    return {"기초": 0.1, "중급": 0.3, "심화": 0.6}

# --- 기출 주입 상한(프롬프트 팽창 방지) ---
PAST_QUESTIONS_CAP = 15

# --- 시드 주입(하이브리드 잠정안: 회전 few-shot 개수) ---
SEED_FEWSHOT_K = 2

# --- MVP 토글 ---
INCLUDE_FOLLOWUP = True
INCLUDE_REVIEW_QUEUE = True
REVIEW_LOOKBACK_DAYS = 7

# 슬랙 질문 push 활성 여부(웹훅 URL 있을 때만). 답안은 절대 전송 안 함(원칙 #2).
SEND_SLACK = bool(SLACK_WEBHOOK_URL)

# --- 출력 언어: 한국어 설명 + 기술용어 원문(영어) 허용 ---
OUTPUT_LANG = "ko"
