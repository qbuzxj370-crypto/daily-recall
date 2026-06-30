"""Notion DB 페이지 생성 (스케줄 자동화 경로: notion-client 토큰 사용).

발행 정본 = Notion DB. 페이지 속성:
  Title(title), Date(date), Category(select=표시명), Difficulty(select),
  Question(rich_text), Kind(select: daily|error).
본문 = renderer.to_notion_blocks(markdown).
"""
from __future__ import annotations

from config import settings, taxonomy
from src import renderer
from src.selector import GenerationContext
from src.state import resolve_data_source_id


def _client():
    from notion_client import Client  # 지연 import
    return Client(auth=settings.NOTION_API_KEY)


def _ds_id(client, db_id: str) -> str:
    """생성 대상 data source id(설정 우선, 없으면 DB에서 해석)."""
    return settings.NOTION_DATA_SOURCE_ID or resolve_data_source_id(client, db_id)


def _props(title: str, date: str, category_disp: str, difficulty: str,
           question: str, kind: str) -> dict:
    return {
        "Title": {"title": [{"text": {"content": title[:2000]}}]},
        "Date": {"date": {"start": date}},
        "Category": {"select": {"name": category_disp}},
        "Difficulty": {"select": {"name": difficulty}},
        "Question": {"rich_text": [{"text": {"content": question[:2000]}}]},
        "Kind": {"select": {"name": kind}},
    }


def publish(item: dict, ctx: GenerationContext, date: str,
            client=None, db_id: str | None = None) -> dict:
    """daily 페이지 1개 생성. 생성된 page 객체(dict) 반환."""
    client = client or _client()
    db_id = db_id or settings.NOTION_DB_ID
    disp = taxonomy.display_name(item["category"])
    md = renderer.to_markdown(item, ctx, date)
    title = f"{date} · {disp} · {item['difficulty']}"
    return client.pages.create(
        parent={"type": "data_source_id", "data_source_id": _ds_id(client, db_id)},
        properties=_props(title, date, disp, item["difficulty"], item["question"], "daily"),
        children=renderer.to_notion_blocks(md),
    )


def _schema_properties() -> dict:
    """init-db용 DB 속성 스키마(이름·타입). select 옵션은 미리 채워 둔다(자동생성에도 의존 가능)."""
    return {
        "Title": {"title": {}},
        "Date": {"date": {}},
        "Category": {"select": {"options": [{"name": taxonomy.display_name(s)} for s in taxonomy.SLUGS]}},
        "Difficulty": {"select": {"options": [{"name": d} for d in taxonomy.DIFFICULTIES]}},
        "Question": {"rich_text": {}},
        "Kind": {"select": {"options": [{"name": "daily"}, {"name": "error"}]}},
    }


def init_db(parent_page_id: str, client=None,
            title: str = "하루한문 (Daily Recall)") -> dict:
    """부모 페이지 아래에 스키마대로 DB 생성(2025-09 API). 생성된 database 객체 반환.

    부모 페이지는 통합(NOTION_API_KEY)에 공유돼 있어야 한다.
    응답의 id=database id(=NOTION_DB_ID), data_sources[0].id=data source id.
    """
    client = client or _client()
    return client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": title}}],
        initial_data_source={"properties": _schema_properties()},
    )


def publish_error(message: str, date: str,
                  client=None, db_id: str | None = None) -> dict:
    """실패 알림 페이지(Kind=error). #7 알림 = Notion."""
    client = client or _client()
    db_id = db_id or settings.NOTION_DB_ID
    return client.pages.create(
        parent={"type": "data_source_id", "data_source_id": _ds_id(client, db_id)},
        properties={
            "Title": {"title": [{"text": {"content": f"[ERROR] {date}"}}]},
            "Date": {"date": {"start": date}},
            "Kind": {"select": {"name": "error"}},
            "Question": {"rich_text": [{"text": {"content": message[:2000]}}]},
        },
        children=[{
            "object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": message[:2000]}}]},
        }],
    )
