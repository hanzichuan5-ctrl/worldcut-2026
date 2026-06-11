#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from html import unescape
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib import request, error, parse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "prediction_history.sqlite3"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com").rstrip("/")
SEARCH_API_URL = os.getenv("SEARCH_API_URL", "").strip()
APIFOOTBALL_API_KEY = os.getenv("APIFOOTBALL_API_KEY", "").strip()
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "").strip()
FOOTBALL_DATA_TOKEN = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
THESPORTSDB_API_KEY = os.getenv("THESPORTSDB_API_KEY", "3").strip()
APIFOOTBALL_BASE_URL = os.getenv("APIFOOTBALL_BASE_URL", "https://v3.football.api-sports.io").rstrip("/")
ODDS_API_BASE_URL = os.getenv("ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4").rstrip("/")
FOOTBALL_DATA_BASE_URL = os.getenv("FOOTBALL_DATA_BASE_URL", "https://api.football-data.org/v4").rstrip("/")
THESPORTSDB_BASE_URL = os.getenv("THESPORTSDB_BASE_URL", "https://www.thesportsdb.com/api/v1/json").rstrip("/")
SPORTTERY_PROXY_URL = os.getenv("SPORTTERY_PROXY_URL", "").strip()
SPORTTERY_PROXY_URLS = [item.strip() for item in os.getenv("SPORTTERY_PROXY_URLS", "").split(",") if item.strip()]
SPORTTERY_OFFICIAL_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getMatchListV1.qry?clientCode=3001"
SPORTTERY_HTTP_PROXY = os.getenv("SPORTTERY_HTTP_PROXY", "http://127.0.0.1:7890").strip()
CACHE_TTL_SECONDS = 600
PROMPT_VERSION = "casual-v2"
PREDICTION_CACHE: dict[str, dict] = {}
DATA_CACHE: dict[str, dict] = {}
BEIJING_TZ = timezone(timedelta(hours=8))
TEAM_EN = {
    "墨西哥": "Mexico",
    "南非": "South Africa",
    "加拿大": "Canada",
    "卡塔尔": "Qatar",
    "美国": "United States",
    "巴拉圭": "Paraguay",
    "德国": "Germany",
    "库拉索": "Curacao",
    "乌拉圭": "Uruguay",
    "沙特阿拉伯": "Saudi Arabia",
    "日本": "Japan",
    "荷兰": "Netherlands",
    "比利时": "Belgium",
    "埃及": "Egypt",
    "瑞士": "Switzerland",
    "奥地利": "Austria",
    "法国": "France",
    "塞内加尔": "Senegal",
    "阿根廷": "Argentina",
    "阿尔及利亚": "Algeria",
    "意大利": "Italy",
    "澳大利亚": "Australia",
    "挪威": "Norway",
    "加纳": "Ghana",
    "葡萄牙": "Portugal",
    "乌兹别克斯坦": "Uzbekistan",
    "摩洛哥": "Morocco",
    "海地": "Haiti",
    "英格兰": "England",
    "克罗地亚": "Croatia",
    "丹麦": "Denmark",
    "突尼斯": "Tunisia",
    "苏格兰": "Scotland",
    "科特迪瓦": "Ivory Coast",
    "巴西": "Brazil",
    "阿联酋": "United Arab Emirates",
    "西班牙": "Spain",
    "佛得角": "Cape Verde",
    "塞尔维亚": "Serbia",
    "新西兰": "New Zealand",
    "哥伦比亚": "Colombia",
    "北马其顿": "North Macedonia",
    "伊朗": "Iran",
    "牙买加": "Jamaica",
}

SYSTEM_PROMPT = """你正在按 Codex skill `worldcup-2026-predictor` 的方法做 2026 世界杯赛前预测。

硬性规则：
1. 严格区分“已知快照/来源事实”和“模型推断”。
2. 不得编造官方大名单、伤病、球员年龄身高、赛果、小组排名、新闻或更衣室消息。
3. 如果页面快照没有提供某项实时资料，必须写“当前快照未提供，需赛前联网补充”，不能用假事实填空。
4. 仍然要给出最终预测，但置信度必须因缺失资料而下调或说明风险。
5. 输出中文，结构清晰，面向页面展开阅读。
6. 直接给结论，不要输出“好的”“我将按照”“下面是分析”“作为AI”等开场白或过程声明。
7. 语气自然、口语化一点，但不要牺牲判断严谨性。"""

RULES = """worldcup-2026-predictor skill 分析流程：
1. 搜集小组赛赛程、已结束比赛结果和小组赛排名。
2. 搜集指定球队信息：官方宣布大名单；球员年龄、身高、近期伤病及影响；更衣室影响球队的消息；其他负面消息；当家球星状态；球队综合实力；球队整体状态。
3. 基于球队信息和对手信息预测该场比赛。
4. 基于小组赛排名预测淘汰赛首轮对阵，但不计算最佳第三名。
5. 考虑球队确保晋级时，是否可能为了淘汰赛路径更有利而放弃第一、选择第二；不得断言故意输球，只能表述为轮换/风险管理/名次动机。
6. 综合以上因素给出最终预测结果。

当前页面基础评分规则：
- 基本面轨道50%：球队实力层级25%，球队/球员状态15%，赛程场地与晋级动机10%。
- 市场/舆情轨道35%：赔率与盘口方向20%，新闻导向10%，公众热度/异常信号5%。
- 裁判与比赛控制15%：裁判执法严谨度、牌点倾向、犯规尺度、VAR/点球风险。

双轨背离预测：
- 基本面轨道和市场/舆情轨道同向：提高置信度。
- 基本面支持一方，但赔率或新闻导向支持另一方：标记“背离”，降低置信度并解释可能原因。
- 裁判严谨度高时，提高红黄牌、点球、定位球和弱队守平概率的权重。

置信度分档：极高=胜率约75%以上；高=63%-74%；中高=55%-62%；中=低于55%或平局权重高。"""


def beijing_time() -> str:
    return datetime.now(BEIJING_TZ).strftime("%Y-%m-%d %H:%M 北京时间")


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                match_id TEXT NOT NULL,
                home TEXT,
                away TEXT,
                match_date TEXT,
                match_time TEXT,
                static_score TEXT,
                summary TEXT,
                analysis TEXT NOT NULL,
                sources_json TEXT,
                model TEXT,
                prompt_version TEXT,
                generated_at TEXT NOT NULL,
                created_ts REAL NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()}
        if "prompt_version" not in columns:
            conn.execute("ALTER TABLE predictions ADD COLUMN prompt_version TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_match_id ON predictions(match_id, created_ts DESC)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sim_accounts (
                account_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_ts REAL NOT NULL
            )
            """
        )


def cache_key(match: dict) -> str:
    base_key = str(match.get("id") or f"{match.get('home', '')}-{match.get('away', '')}-{match.get('d', '')}-{match.get('time', '')}")
    return f"{PROMPT_VERSION}:{base_key}"


def match_id_key(match: dict) -> str:
    return str(match.get("id") or f"{match.get('home', '')}-{match.get('away', '')}-{match.get('d', '')}-{match.get('time', '')}")


def get_prediction(api_key: str, match: dict) -> dict:
    key = cache_key(match)
    match_id = match_id_key(match)
    now = datetime.now(timezone.utc).timestamp()
    cached = PREDICTION_CACHE.get(key)
    if cached and now - cached["ts"] < CACHE_TTL_SECONDS:
        payload = dict(cached["payload"])
        payload["cached"] = True
        payload["cache_source"] = "memory"
        return payload
    persisted = get_recent_prediction_payload(match_id, CACHE_TTL_SECONDS, prompt_version=PROMPT_VERSION)
    if persisted:
        PREDICTION_CACHE[key] = {"ts": now, "payload": persisted}
        payload = dict(persisted)
        payload["cached"] = True
        payload["cache_source"] = "sqlite"
        return payload
    intelligence = collect_match_intelligence(match)
    analysis = call_openai(api_key, match, intelligence)
    payload = {
        "id": match.get("id"),
        "analysis": analysis,
        "summary": summarize_analysis(analysis),
        "sources": intelligence,
        "model": MODEL,
        "generated_at": beijing_time(),
        "cached": False,
    }
    save_prediction(match, payload)
    PREDICTION_CACHE[key] = {"ts": now, "payload": payload}
    return payload


def get_recent_prediction_payload(match_id: str, max_age_seconds: int, prompt_version: str | None = None) -> dict | None:
    cutoff = datetime.now(timezone.utc).timestamp() - max_age_seconds
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM predictions
            WHERE match_id = ? AND created_ts >= ? AND (? IS NULL OR prompt_version = ?)
            ORDER BY created_ts DESC
            LIMIT 1
            """,
            (str(match_id), cutoff, prompt_version, prompt_version),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    try:
        sources = json.loads(item.get("sources_json") or "[]")
    except json.JSONDecodeError:
        sources = []
    return {
        "id": int(match_id) if str(match_id).isdigit() else match_id,
        "analysis": item.get("analysis", ""),
        "summary": item.get("summary", ""),
        "sources": sources,
        "model": item.get("model", MODEL),
        "generated_at": item.get("generated_at", ""),
        "cached": True,
    }


def save_prediction(match: dict, payload: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO predictions (
                match_id, home, away, match_date, match_time, static_score,
                summary, analysis, sources_json, model, prompt_version, generated_at, created_ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(match.get("id", "")),
                match.get("home", ""),
                match.get("away", ""),
                match.get("d", ""),
                match.get("time", ""),
                match.get("score", ""),
                payload.get("summary", ""),
                payload.get("analysis", ""),
                json.dumps(payload.get("sources", []), ensure_ascii=False),
                payload.get("model", ""),
                PROMPT_VERSION,
                payload.get("generated_at", ""),
                datetime.now(timezone.utc).timestamp(),
            ),
        )


def get_history(match_id: str | None = None, limit: int = 50) -> list[dict]:
    limit = max(1, min(limit, 200))
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if match_id:
            rows = conn.execute(
                """
                SELECT * FROM predictions
                WHERE match_id = ?
                ORDER BY created_ts DESC
                LIMIT ?
                """,
                (str(match_id), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM predictions
                ORDER BY created_ts DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["sources"] = json.loads(item.pop("sources_json") or "[]")
        except json.JSONDecodeError:
            item["sources"] = []
        item["predicted_score"] = extract_predicted_score(item.get("analysis", "")) or item.get("static_score", "")
        result.append(item)
    return result


def default_sim_state(account_id: str) -> dict:
    return {
        "account_id": account_id,
        "account": {"initial": 10000, "cash": 10000, "bets": []},
        "history": [],
        "last_signature": "",
        "updated_at": beijing_time(),
    }


def get_sim_state(account_id: str | None) -> dict:
    account_id = re.sub(r"[^a-zA-Z0-9_-]", "", account_id or "")[:48] or uuid.uuid4().hex[:12]
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT state_json FROM sim_accounts WHERE account_id = ?", (account_id,)).fetchone()
    if not row:
        state = default_sim_state(account_id)
        save_sim_state(state)
        return state
    try:
        state = json.loads(row["state_json"])
    except json.JSONDecodeError:
        state = default_sim_state(account_id)
    state["account_id"] = account_id
    return state


def save_sim_state(state: dict) -> dict:
    account_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(state.get("account_id") or ""))[:48] or uuid.uuid4().hex[:12]
    account = state.get("account") if isinstance(state.get("account"), dict) else {"initial": 10000, "cash": 10000, "bets": []}
    history = state.get("history") if isinstance(state.get("history"), list) else []
    safe_state = {
        "account_id": account_id,
        "account": account,
        "history": history[:50],
        "last_signature": str(state.get("last_signature") or "")[:8000],
        "updated_at": beijing_time(),
    }
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO sim_accounts (account_id, state_json, updated_at, updated_ts)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                state_json = excluded.state_json,
                updated_at = excluded.updated_at,
                updated_ts = excluded.updated_ts
            """,
            (
                account_id,
                json.dumps(safe_state, ensure_ascii=False),
                safe_state["updated_at"],
                datetime.now(timezone.utc).timestamp(),
            ),
        )
    return safe_state


def summarize_analysis(text: str) -> str:
    lines = [line.strip(" -•") for line in text.splitlines() if line.strip()]
    useful = [line for line in lines if any(word in line for word in ("结论", "推荐", "概率", "比分", "竞猜", "置信"))]
    return "；".join(useful[:3])[:220] or text[:220]


def extract_predicted_score(text: str) -> str:
    patterns = [
        r"推荐比分[：:]\s*([^\n；;，,]+)",
        r"比分[：:]\s*([^\n；;，,]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip().strip("*")
    return ""


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_json_cached(url: str, ttl_seconds: int = 1800) -> dict:
    now = datetime.now(timezone.utc).timestamp()
    cached = DATA_CACHE.get(url)
    if cached and now - cached["ts"] < ttl_seconds:
        return cached["data"]
    req = request.Request(url, headers={"User-Agent": "worldcup-predictions/1.0"})
    with request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    DATA_CACHE[url] = {"ts": now, "data": data}
    return data


def fetch_json_request_cached(url: str, headers: dict | None = None, ttl_seconds: int = 900, timeout_seconds: int = 25, proxy_url: str = "") -> dict:
    cache_id = json.dumps({"url": url, "headers": sorted((headers or {}).items()), "proxy": proxy_url}, sort_keys=True)
    now = datetime.now(timezone.utc).timestamp()
    cached = DATA_CACHE.get(cache_id)
    if cached and now - cached["ts"] < ttl_seconds:
        return cached["data"]
    req = request.Request(url, headers=headers or {"User-Agent": "worldcup-predictions/1.0"})
    opener = request.build_opener(request.ProxyHandler({"http": proxy_url, "https": proxy_url})) if proxy_url else request.build_opener()
    with opener.open(req, timeout=timeout_seconds) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    DATA_CACHE[cache_id] = {"ts": now, "data": data}
    return data


def unwrap_proxy_json(data: dict) -> dict:
    if isinstance(data, dict) and isinstance(data.get("contents"), str):
        try:
            return json.loads(data["contents"])
        except json.JSONDecodeError:
            return data
    if isinstance(data, dict) and isinstance(data.get("body"), str):
        try:
            return json.loads(data["body"])
        except json.JSONDecodeError:
            return data
    return data


def fetch_text_cached(url: str, ttl_seconds: int = 86400) -> str:
    now = datetime.now(timezone.utc).timestamp()
    cached = DATA_CACHE.get(url)
    if cached and now - cached["ts"] < ttl_seconds:
        return cached["data"]
    req = request.Request(url, headers={"User-Agent": "worldcup-predictions/1.0"})
    with request.urlopen(req, timeout=25) as resp:
        data = resp.read().decode("utf-8", errors="ignore")
    DATA_CACHE[url] = {"ts": now, "data": data}
    return data


def normalize_sporttery_decimal(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"-", "--", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def decimal_to_american(decimal_odds: float | None) -> int | None:
    if not decimal_odds or decimal_odds <= 1:
        return None
    if decimal_odds >= 2:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def sporttery_pick(row: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    return None


def parse_sporttery_matches(data: dict) -> list[dict]:
    matches = []
    for row in walk_json(data):
        home = sporttery_pick(row, ("homeTeam", "homeTeamName", "homeTeamAbbName", "homeTeamAllName", "hostName", "homeName", "h_cn", "home_team"))
        away = sporttery_pick(row, ("awayTeam", "awayTeamName", "awayTeamAbbName", "awayTeamAllName", "guestName", "awayName", "a_cn", "away_team"))
        if not home or not away:
            continue
        had = row.get("had") or row.get("HAD") or row.get("spf") or row.get("odds") or {}
        odds_list = row.get("oddsList")
        if isinstance(odds_list, list):
            for odds_item in odds_list:
                if str(odds_item.get("poolCode", "")).upper() == "HAD":
                    had = odds_item
                    break
        if isinstance(had, list) and had:
            had = had[0]
        if not isinstance(had, dict):
            had = row
        win = normalize_sporttery_decimal(sporttery_pick(had, ("h", "home", "win", "had_h", "h_sp", "a")))
        draw = normalize_sporttery_decimal(sporttery_pick(had, ("d", "draw", "had_d", "d_sp", "b")))
        lose = normalize_sporttery_decimal(sporttery_pick(had, ("a", "away", "lose", "had_a", "a_sp", "c")))
        if not all([win, draw, lose]):
            continue
        matches.append({
            "home": str(home),
            "away": str(away),
            "league": sporttery_pick(row, ("leagueName", "leagueAbbName", "leagueAllName", "league", "l_cn")),
            "match_no": sporttery_pick(row, ("matchNumStr", "matchNum", "matchNo", "num", "issueNum")),
            "match_date": sporttery_pick(row, ("matchDate", "businessDate", "date")),
            "match_clock": sporttery_pick(row, ("matchTime", "time")),
            "match_time": " ".join(str(part) for part in (
                sporttery_pick(row, ("matchDate", "businessDate", "date")),
                sporttery_pick(row, ("matchTime", "time")),
            ) if part),
            "decimal": [win, draw, lose],
            "american": [decimal_to_american(win), decimal_to_american(draw), decimal_to_american(lose)],
            "source": "中国体育彩票竞彩网固定奖金",
        })
    return matches


def build_sporttery_urls() -> list[str]:
    urls = []
    for raw_url in [SPORTTERY_PROXY_URL, *SPORTTERY_PROXY_URLS, SPORTTERY_OFFICIAL_URL]:
        if not raw_url:
            continue
        if "{url}" in raw_url:
            raw_url = raw_url.replace("{url}", parse.quote(SPORTTERY_OFFICIAL_URL, safe=""))
        if raw_url not in urls:
            urls.append(raw_url)
    return urls


def sporttery_fetch_payload() -> tuple[dict | None, str, str]:
    errors = []
    for url in build_sporttery_urls():
        try:
            use_proxy = bool(SPORTTERY_HTTP_PROXY) and url == SPORTTERY_OFFICIAL_URL
            data = fetch_json_request_cached(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                "Referer": "https://www.sporttery.cn/",
                "Origin": "https://www.sporttery.cn",
                "Accept": "application/json,text/plain,*/*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }, ttl_seconds=600, timeout_seconds=8, proxy_url=SPORTTERY_HTTP_PROXY if use_proxy else "")
            return unwrap_proxy_json(data), url, ""
        except Exception as exc:
            errors.append(f"{url}: {str(exc)[:180]}")
    source_url = build_sporttery_urls()[0] if build_sporttery_urls() else SPORTTERY_OFFICIAL_URL
    return None, source_url, " | ".join(errors)


def sporttery_odds_snapshot() -> dict:
    data, url, err = sporttery_fetch_payload()
    if data is None:
        return {
            "source": "中国体育彩票竞彩网",
            "source_url": url,
            "status": "blocked_or_unavailable",
            "note": "已接入免费体彩网关，但当前服务器访问被站点安全策略拦截或网络不可用。可配置 SPORTTERY_PROXY_URL 或 SPORTTERY_PROXY_URLS；支持直接 JSON，也支持 AllOrigins contents 包装格式和 {url} 模板。",
            "error": err[:300],
            "matches": [],
            "generated_at": beijing_time(),
            "official_url": SPORTTERY_OFFICIAL_URL,
        }
    matches = parse_sporttery_matches(data)
    return {
        "source": "中国体育彩票竞彩网",
        "source_url": url,
        "status": "ok" if matches else "no_matches_parsed",
        "note": "固定奖金为十进制赔率，前端会换算成美式赔率用于原模拟盘。",
        "matches": matches[:200],
        "raw_count": len(matches),
        "generated_at": beijing_time(),
        "official_url": SPORTTERY_OFFICIAL_URL,
    }


def sporttery_tool(home_cn: str, away_cn: str) -> list[dict]:
    snapshot = sporttery_odds_snapshot()
    items = []
    for item in snapshot.get("matches", []):
        text = f"{item.get('home', '')} {item.get('away', '')}"
        if home_cn in text or away_cn in text:
            items.append(item)
    return [{
        "type": "sporttery_fixed_bonus_snapshot",
        "source": "中国体育彩票竞彩网",
        "status": snapshot.get("status"),
        "source_url": snapshot.get("source_url"),
        "note": snapshot.get("note"),
        "items": items[:5],
        "error": snapshot.get("error"),
    }]


def search_tool(query: str, limit: int = 3) -> list[dict]:
    if not SEARCH_API_URL:
        return [{
            "query": query,
            "status": "search_api_not_configured",
            "note": "后端未配置 SEARCH_API_URL；LLM 只能使用页面快照和内置官方来源，不能假装已完成实时搜索。",
        }]

    url = SEARCH_API_URL + ("&" if "?" in SEARCH_API_URL else "?") + parse.urlencode({"q": query, "limit": limit})
    req = request.Request(url, headers={"User-Agent": "worldcup-predictions/1.0"})
    try:
        with request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return [{"query": query, "error": str(exc)}]

    results = []
    raw_items = data.get("results") or data.get("data") or []
    for item in raw_items[:limit]:
        results.append({
            "query": query,
            "title": strip_tags(str(item.get("title", ""))),
            "url": str(item.get("url", "")),
            "snippet": strip_tags(str(item.get("snippet") or item.get("content") or "")),
        })
    return results or [{"query": query, "error": "no results"}]


def worldcup26_tool(home: str, away: str) -> list[dict]:
    results: list[dict] = []
    try:
        teams_data = fetch_json_cached("https://worldcup26.ir/get/teams")
        games_data = fetch_json_cached("https://worldcup26.ir/get/games")
        groups_data = fetch_json_cached("https://worldcup26.ir/get/groups")
    except Exception as exc:
        return [{"type": "worldcup26_api_error", "error": str(exc)}]

    teams = teams_data.get("teams", [])
    by_id = {str(t.get("id")): t for t in teams}
    by_name = {t.get("name_en"): t for t in teams}
    home_team = by_name.get(home)
    away_team = by_name.get(away)

    for game in games_data.get("games", []):
        names = {game.get("home_team_name_en"), game.get("away_team_name_en")}
        if home in names and away in names:
            results.append({
                "type": "2026_fixture_result",
                "source": "worldcup26.ir",
                "group": game.get("group"),
                "matchday": game.get("matchday"),
                "local_date": game.get("local_date"),
                "home": game.get("home_team_name_en"),
                "away": game.get("away_team_name_en"),
                "score": f"{game.get('home_score')}-{game.get('away_score')}",
                "finished": game.get("finished"),
                "status": game.get("time_elapsed"),
            })

    wanted_groups = {t.get("groups") for t in (home_team, away_team) if t}
    for group in groups_data.get("groups", []):
        if group.get("name") not in wanted_groups:
            continue
        standings = []
        for row in group.get("teams", []):
            team = by_id.get(str(row.get("team_id")), {})
            standings.append({
                "team": team.get("name_en", row.get("team_id")),
                "mp": row.get("mp"),
                "w": row.get("w"),
                "d": row.get("d"),
                "l": row.get("l"),
                "pts": row.get("pts"),
                "gf": row.get("gf"),
                "ga": row.get("ga"),
                "gd": row.get("gd"),
            })
        results.append({
            "type": "2026_group_standings",
            "source": "worldcup26.ir",
            "group": group.get("name"),
            "standings": standings,
        })
    return results


def openfootball_schedule_tool(home: str, away: str) -> list[dict]:
    try:
        data = fetch_json_cached("https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json")
    except Exception as exc:
        return [{"type": "openfootball_schedule_error", "error": str(exc)}]
    results = []
    for match in data.get("matches", []):
        names = {match.get("team1"), match.get("team2")}
        if home in names and away in names:
            results.append({
                "type": "2026_fixture_source",
                "source": "openfootball/worldcup.json",
                "round": match.get("round"),
                "date": match.get("date"),
                "time": match.get("time"),
                "home": match.get("team1"),
                "away": match.get("team2"),
                "group": match.get("group"),
                "ground": match.get("ground"),
            })
    return results


def historical_results_tool(home: str, away: str, limit: int = 8) -> list[dict]:
    url = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
    try:
        csv_text = fetch_text_cached(url)
    except Exception as exc:
        return [{"type": "historical_results_error", "error": str(exc)}]
    rows = []
    for line in csv_text.splitlines()[1:]:
        parts = line.split(",")
        if len(parts) < 9:
            continue
        date, home_team, away_team, home_score, away_score, tournament, city, country, neutral = parts[:9]
        if {home_team, away_team} == {home, away}:
            rows.append({
                "type": "head_to_head_result",
                "source": "martj42/international_results",
                "date": date,
                "home": home_team,
                "away": away_team,
                "score": f"{home_score}-{away_score}",
                "tournament": tournament,
                "city": city,
                "country": country,
                "neutral": neutral,
            })
    recent_home = []
    recent_away = []
    for line in reversed(csv_text.splitlines()[1:]):
        parts = line.split(",")
        if len(parts) < 9:
            continue
        date, home_team, away_team, home_score, away_score, tournament, city, country, neutral = parts[:9]
        item = {
            "type": "recent_team_result",
            "source": "martj42/international_results",
            "date": date,
            "home": home_team,
            "away": away_team,
            "score": f"{home_score}-{away_score}",
            "tournament": tournament,
        }
        if len(recent_home) < 5 and home in (home_team, away_team):
            recent_home.append(item)
        if len(recent_away) < 5 and away in (home_team, away_team):
            recent_away.append(item)
        if len(recent_home) >= 5 and len(recent_away) >= 5:
            break
    return rows[-limit:] + recent_home + recent_away


def thesportsdb_tool(home: str, away: str) -> list[dict]:
    key = THESPORTSDB_API_KEY or "3"
    results = []
    endpoints = [
        ("team_home", f"{THESPORTSDB_BASE_URL}/{key}/searchteams.php?{parse.urlencode({'t': home})}"),
        ("team_away", f"{THESPORTSDB_BASE_URL}/{key}/searchteams.php?{parse.urlencode({'t': away})}"),
        ("event_search", f"{THESPORTSDB_BASE_URL}/{key}/searchevents.php?{parse.urlencode({'e': f'{home}_vs_{away}'})}"),
    ]
    for label, url in endpoints:
        try:
            data = fetch_json_request_cached(url, ttl_seconds=1800)
            results.append({
                "type": f"thesportsdb_{label}",
                "source": "TheSportsDB free API",
                "items": (data.get("teams") or data.get("event") or data.get("events") or [])[:3],
            })
        except Exception as exc:
            results.append({"type": f"thesportsdb_{label}_error", "source": "TheSportsDB free API", "error": str(exc)})
    return results


def football_data_tool(home: str, away: str) -> list[dict]:
    if not FOOTBALL_DATA_TOKEN:
        return [{
            "type": "football_data_not_configured",
            "source": "football-data.org free tier",
            "note": "Set FOOTBALL_DATA_TOKEN to fetch free-tier fixtures, scores and standings where competition coverage is available.",
        }]
    headers = {"X-Auth-Token": FOOTBALL_DATA_TOKEN, "User-Agent": "worldcup-predictions/1.0"}
    results = []
    endpoints = [
        ("competitions", f"{FOOTBALL_DATA_BASE_URL}/competitions"),
        ("matches", f"{FOOTBALL_DATA_BASE_URL}/matches"),
    ]
    for label, url in endpoints:
        try:
            data = fetch_json_request_cached(url, headers=headers, ttl_seconds=900)
            results.append({
                "type": f"football_data_{label}",
                "source": "football-data.org free tier",
                "items": data.get("competitions", data.get("matches", []))[:5],
            })
        except Exception as exc:
            results.append({"type": f"football_data_{label}_error", "source": "football-data.org free tier", "error": str(exc)})
    return results


def api_football_tool(home: str, away: str) -> list[dict]:
    if not APIFOOTBALL_API_KEY:
        return [{
            "type": "api_football_free_tier_not_configured",
            "source": "API-Football free tier",
            "note": "Set APIFOOTBALL_API_KEY to use the free tier for fixtures, standings, lineups, injuries, predictions and odds where available.",
        }]
    headers = {"x-apisports-key": APIFOOTBALL_API_KEY}
    results = []
    endpoints = [
        ("fixtures_search", f"{APIFOOTBALL_BASE_URL}/fixtures?season=2026&search={parse.quote(home)}"),
        ("injuries_home", f"{APIFOOTBALL_BASE_URL}/injuries?season=2026&team={parse.quote(home)}"),
        ("injuries_away", f"{APIFOOTBALL_BASE_URL}/injuries?season=2026&team={parse.quote(away)}"),
        ("odds", f"{APIFOOTBALL_BASE_URL}/odds?season=2026&search={parse.quote(home + ' ' + away)}"),
    ]
    for label, url in endpoints:
        try:
            data = fetch_json_request_cached(url, headers=headers, ttl_seconds=900)
            results.append({
                "type": f"api_football_{label}",
                "source": "API-Football free tier",
                "response_count": data.get("results"),
                "items": (data.get("response") or [])[:3],
            })
        except Exception as exc:
            results.append({"type": f"api_football_{label}_error", "source": "API-Football free tier", "error": str(exc)})
    return results


def odds_api_tool(home: str, away: str) -> list[dict]:
    if not ODDS_API_KEY:
        return [{
            "type": "odds_api_not_configured",
            "source": "The Odds API",
            "note": "Set ODDS_API_KEY to fetch bookmaker odds and market movement snapshots.",
        }]
    # Soccer sport keys vary by provider availability; this endpoint is intentionally configurable.
    sport_key = os.getenv("ODDS_API_SPORT", "soccer_fifa_world_cup")
    query = parse.urlencode({
        "apiKey": ODDS_API_KEY,
        "regions": os.getenv("ODDS_API_REGIONS", "us,eu,uk"),
        "markets": os.getenv("ODDS_API_MARKETS", "h2h"),
        "oddsFormat": os.getenv("ODDS_API_FORMAT", "american"),
    })
    url = f"{ODDS_API_BASE_URL}/sports/{sport_key}/odds?{query}"
    try:
        data = fetch_json_request_cached(url, ttl_seconds=600)
    except Exception as exc:
        return [{"type": "odds_api_error", "source": "The Odds API", "error": str(exc)}]
    matches = []
    for item in data if isinstance(data, list) else []:
        teams = {item.get("home_team"), item.get("away_team")}
        if home in teams or away in teams or home in str(item) or away in str(item):
            matches.append(item)
    return [{
        "type": "odds_api_market_snapshot",
        "source": "The Odds API",
        "sport_key": sport_key,
        "home": home,
        "away": away,
        "items": matches[:3],
        "raw_count": len(data) if isinstance(data, list) else None,
    }]


def collect_match_intelligence(match: dict) -> list[dict]:
    home_cn = match.get("home", "")
    away_cn = match.get("away", "")
    home = TEAM_EN.get(match.get("home", ""), match.get("home", ""))
    away = TEAM_EN.get(match.get("away", ""), match.get("away", ""))
    collected = [
        {
            "type": "official_source",
            "title": "FIFA official match schedule, fixtures and results",
            "url": "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums",
            "snippet": "Use for official fixture, result, venue and tournament context checks.",
        },
        {
            "type": "official_source",
            "title": "FIFA men's world ranking",
            "url": "https://inside.fifa.com/fifa-world-ranking/men",
            "snippet": "Use for team strength baseline and ranking comparison.",
        },
        {
            "type": "schedule_market_source",
            "title": "ESPN FIFA World Cup schedule",
            "url": "https://www.espn.com/soccer/schedule/_/league/fifa.world",
            "snippet": "Use for schedule display, venue/time checks and market-line snapshot when available.",
        },
    ]
    collected.extend(worldcup26_tool(home, away))
    collected.extend(openfootball_schedule_tool(home, away))
    collected.extend(historical_results_tool(home, away))
    collected.extend(thesportsdb_tool(home, away))
    collected.extend(football_data_tool(home, away))
    collected.extend(api_football_tool(home, away))
    collected.extend(odds_api_tool(home, away))
    collected.extend(sporttery_tool(home_cn, away_cn))
    queries = [
        f"{home} {away} 2026 World Cup fixture group standings result",
        f"{home} national team official squad injuries 2026 World Cup",
        f"{away} national team official squad injuries 2026 World Cup",
        f"{home} {away} recent form FIFA ranking 2026",
        f"{home} {away} locker room negative news injury report",
        f"{home} {away} referee assignment strictness cards penalties odds movement news",
    ]
    seen = {item.get("url") or json.dumps(item, ensure_ascii=False, sort_keys=True) for item in collected}
    for query in queries:
        for item in search_tool(query, limit=2):
            key = item.get("url") or item.get("error") or item.get("title")
            if key in seen:
                continue
            seen.add(key)
            collected.append(item)
    return collected[:36]


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0].split("#", 1)[0]
        rel = path.lstrip("/") or "index.html"
        return str(ROOT / rel)

    def do_GET(self) -> None:
        parsed = parse.urlparse(self.path)
        if parsed.path == "/api/odds":
            json_response(self, 200, sporttery_odds_snapshot())
            return
        if parsed.path == "/api/history":
            params = parse.parse_qs(parsed.query)
            match_id = params.get("match_id", [""])[0] or None
            try:
                limit = int(params.get("limit", ["50"])[0])
            except ValueError:
                limit = 50
            json_response(self, 200, {"history": get_history(match_id=match_id, limit=limit)})
            return
        if parsed.path == "/api/sim/account":
            params = parse.parse_qs(parsed.query)
            json_response(self, 200, get_sim_state(params.get("account_id", [""])[0]))
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path == "/api/sim/save":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                json_response(self, 200, save_sim_state(payload))
            except Exception as exc:
                json_response(self, 500, {"error": str(exc)})
            return

        if self.path not in ("/api/predict", "/api/predictions", "/api/auto-bet"):
            json_response(self, 404, {"error": "接口不存在"})
            return

        key = os.getenv("OPENAI_API_KEY")
        if not key:
            json_response(self, 503, {"error": "服务器未配置 OPENAI_API_KEY，无法调用 LLM。"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/auto-bet":
                result = get_auto_bet_plan(key, payload)
                json_response(self, 200, result)
                return
            if self.path == "/api/predict":
                result = get_prediction(key, payload.get("match") or {})
                json_response(self, 200, result)
                return

            matches = payload.get("matches") or []
            limit = int(payload.get("limit") or len(matches))
            results = []
            for match in matches[:limit]:
                try:
                    results.append(get_prediction(key, match))
                except Exception as exc:
                    results.append({"id": match.get("id"), "error": str(exc), "generated_at": beijing_time(), "model": MODEL})
            json_response(self, 200, {"results": results, "model": MODEL, "generated_at": beijing_time()})
        except Exception as exc:
            json_response(self, 500, {"error": str(exc)})


def extract_json_object(text: str) -> dict:
    text = text.strip()
    tagged = re.search(r"<json>\s*(.*?)\s*</json>", text, re.S | re.I)
    if tagged:
        text = tagged.group(1).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def call_llm_json(api_key: str, prompt: str, max_tokens: int = 2200) -> tuple[dict, str]:
    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "你是结构化输出代理。必须把唯一 JSON 放在 <json> 和 </json> 标签之间，不要输出标签外文本。",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    req = request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = data["choices"][0]["message"]["content"].strip()
    try:
        return extract_json_object(text), text
    except Exception:
        repair_prompt = f"""下面这段文本本应包含一个 JSON 对象。请只输出修复后的 JSON，并放在 <json></json> 中。

要求：
- 顶层对象只能包含 summary 和 bets。
- bets 必须是数组。
- 不要添加解释。

原始文本：
{text[:6000]}
"""
        repair_body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": "只输出 <json>...</json>，其中必须是合法 JSON。"},
                {"role": "user", "content": repair_prompt},
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        repair_req = request.Request(
            f"{BASE_URL}/v1/chat/completions",
            data=json.dumps(repair_body).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(repair_req, timeout=45) as resp:
            repair_data = json.loads(resp.read().decode("utf-8"))
        repaired = repair_data["choices"][0]["message"]["content"].strip()
        return extract_json_object(repaired), repaired


def get_auto_bet_plan(api_key: str, payload: dict) -> dict:
    matches = payload.get("matches") or []
    settings = payload.get("settings") or {}
    bankroll = float(settings.get("cash") or settings.get("bankroll") or 0)
    max_stake_pct = float(settings.get("maxStakePct") or 5)
    min_edge_pct = float(settings.get("minEdgePct") or 2)
    compact = []
    for match in matches[:40]:
        compact.append({
            "id": match.get("id"),
            "date": match.get("d"),
            "match": f"{match.get('home')} vs {match.get('away')}",
            "home": match.get("home"),
            "away": match.get("away"),
            "odds_decimal": match.get("oddsDecimal") or [],
            "odds_american": match.get("odds") or [],
            "page_probabilities": match.get("probs") or [],
            "page_pick": match.get("api"),
            "confidence": match.get("conf"),
            "source": match.get("oddsSource"),
        })
    prompt = f"""你是 2026 世界杯模拟盘自动下注代理。

目标：基于 worldcup-2026-predictor skill 的思路，结合体彩固定奖金、页面概率、球队实力推断、新闻/裁判/阵容缺失风险，给出模拟下注计划。这里是研究型模拟盘，不是真实资金，不要因为信息不完整就全部跳过。

硬性限制：
- 这是模拟盘，不是真实下注。
- 不得编造伤病、裁判、新闻、大名单；缺失信息视为风险，降低下注金额。
- 只允许选择 主胜、平局、客胜 或 跳过。
- 单场下注不能超过可用资金的 {max_stake_pct}%。
- 体彩固定奖金天然含水位，页面概率多为盘口隐含概率归一化；不要机械要求每场都有严格数学正期望。
- 优先选择 3-6 场强信号小仓试单，除非整批比赛确实没有任何清晰倾向。
- 强信号定义：热门方胜率/实力层级明显、赔率没有严重过热、或弱势方向有清晰背离价值。
- 信息缺失时降低仓位，不要直接跳过所有比赛。
- 单场常规下注建议为可用资金的 0.5%-2.0%；极强信号最多到 {max_stake_pct}%。
- 总下注金额建议控制在可用资金的 8%-18%，最高不超过 35%。
- 输出必须把唯一 JSON 放在 <json> 和 </json> 标签之间。
- 标签外不要写任何文字。
- JSON 里不要出现注释、尾随逗号、NaN、Infinity。

可用资金：{bankroll}
设置：{json.dumps(settings, ensure_ascii=False)}
比赛列表：{json.dumps(compact, ensure_ascii=False)}

输出格式：
<json>
{{
  "summary": "一句话说明整体策略",
  "bets": [
    {{
      "id": "比赛id",
      "pick": "主胜|平局|客胜|跳过",
      "probability": 0.62,
      "edge_pct": 4.2,
      "stake": 120,
      "reason": "20-50字中文理由"
    }}
  ]
}}
</json>
"""
    try:
        plan, text = call_llm_json(api_key, prompt, max_tokens=2200)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return fallback_auto_bet_plan(matches, settings, f"LLM API 错误 {exc.code}: {detail[:180]}")
    except Exception as exc:
        return fallback_auto_bet_plan(matches, settings, f"LLM 自动下注计划解析失败：{exc}")

    safe_bets = []
    remaining = bankroll
    max_single = bankroll * max_stake_pct / 100
    match_ids = {str(match.get("id")) for match in matches}
    for item in plan.get("bets", []):
        if str(item.get("id")) not in match_ids:
            continue
        pick = item.get("pick")
        if pick not in ("主胜", "平局", "客胜"):
            continue
        try:
            stake = max(0, min(float(item.get("stake") or 0), max_single, remaining))
        except (TypeError, ValueError):
            stake = 0
        if stake <= 0:
            continue
        remaining -= stake
        item["stake"] = round(stake)
        safe_bets.append(item)
    if len(safe_bets) < 3:
        fallback = fallback_auto_bet_plan(matches, {**settings, "cash": remaining, "bankroll": bankroll}, "LLM给出的下注少于3单")
        used_ids = {str(item.get("id")) for item in safe_bets}
        for item in fallback.get("bets", []):
            if len(safe_bets) >= 3:
                break
            if str(item.get("id")) in used_ids:
                continue
            safe_bets.append(item)
            used_ids.add(str(item.get("id")))
        if len(safe_bets) > len(plan.get("bets", [])):
            plan["summary"] = f"{plan.get('summary') or 'LLM已生成计划'}；因下注数量过少，已用强信号小仓策略补足。"
    return {
        "summary": str(plan.get("summary") or "LLM 已生成模拟下注计划。"),
        "bets": safe_bets,
        "model": MODEL,
        "generated_at": beijing_time(),
    }


def fallback_auto_bet_plan(matches: list[dict], settings: dict, reason: str) -> dict:
    bankroll = float(settings.get("cash") or settings.get("bankroll") or 0)
    max_stake_pct = float(settings.get("maxStakePct") or 5)
    remaining = bankroll
    bets = []
    candidates = []
    for match in matches:
        probs = match.get("probs") or []
        odds = match.get("oddsDecimal") or []
        if len(probs) < 3 or len(odds) < 3:
            continue
        idx = max(range(3), key=lambda i: float(probs[i] or 0))
        pick = ("主胜", "平局", "客胜")[idx]
        prob = float(probs[idx]) / 100
        decimal_odds = float(odds[idx])
        if prob < 0.45 and decimal_odds < 2.0:
            continue
        confidence_score = prob * 100
        if decimal_odds < 1.2:
            confidence_score -= 8
        candidates.append((confidence_score, match, pick, prob, decimal_odds))
    target_count = min(6, max(3, len(candidates) // 3)) if candidates else 0
    for confidence_score, match, pick, prob, decimal_odds in sorted(candidates, reverse=True, key=lambda item: item[0])[:target_count]:
        stake_pct = min(max_stake_pct, 0.5 + max(0, prob - 0.5) * 5)
        stake = min(bankroll * stake_pct / 100, remaining)
        if stake <= 0:
            break
        remaining -= stake
        bets.append({
            "id": match.get("id"),
            "pick": pick,
            "probability": round(prob, 3),
            "edge_pct": round((prob * decimal_odds - 1) * 100, 1),
            "stake": round(stake),
            "reason": "LLM不可用，按强信号小仓试单兜底",
        })
        if bankroll and (bankroll - remaining) / bankroll >= 0.18:
            break
    return {
        "summary": f"{reason}；已使用数学规则兜底生成模拟计划。",
        "bets": bets,
        "model": f"{MODEL} fallback",
        "generated_at": beijing_time(),
    }


def call_openai(api_key: str, match: dict, intelligence: list[dict]) -> str:
    user_prompt = f"""直接给这场 2026 世界杯比赛的预测分析。不要写开场白，不要说“我将按照规则分析”，第一行就进入结论。

比赛快照：
{json.dumps(match, ensure_ascii=False, indent=2)}

后端在线情报工具返回的搜索摘要和来源：
{json.dumps(intelligence, ensure_ascii=False, indent=2)}

{RULES}

请按以下结构输出，语气像给懂球但不想看废话的人读：

1. 结论
- 主胜/平局/客胜：
- 推荐比分：
- 胜平负概率：
- 竞猜选项：
- 置信度：

2. 关键依据
- 小组赛赛程/已结束赛果/小组排名：优先使用在线情报工具里的可靠来源；没有可靠结果就标注需补充。
- 双方官方大名单与球员状态：说明大名单、年龄身高、伤病、更衣室/负面消息、当家球星状态是否已知；在线情报没有给出就不要编造。
- 双方综合实力与整体状态：基于快照和通用实力层级做推断，并标明这是推断。
- 对手信息如何影响本场：写出 2-3 个具体对位因素。
- 淘汰赛首轮路径与名次动机：如果当前排名/出线形势未知，明确写无法判断；如果可推断动机，也必须说明依据。
- 综合结论：说明是否调整静态卡片预测。

3. 双轨背离
- 基本面轨道50%：球队实力、球员状态、赛程场地、晋级动机。
- 市场/舆情轨道35%：赔率/盘口方向、新闻导向、公众热度或异常信号。
- 裁判与比赛控制15%：裁判执法严谨度、牌点倾向、犯规尺度、VAR/点球风险；若当前快照未提供裁判信息，必须标注需赛前联网补充。
- 双轨背离判断：基本面轨道与市场/舆情轨道是同向、轻微背离还是强背离？背离时最终预测如何修正？

4. 临场复核清单
- 列出 3-6 个赛前必须联网确认的信息，必须包含裁判信息、赔率变化、新闻导向。

限制：不要编造当前伤病、最终名单、已结束赛果、小组排名、球员年龄身高或新闻；缺失就明确写“当前快照未提供，需赛前联网补充”。禁止输出“好的，我将按照...”这类套话。"""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1800,
    }
    req = request.Request(
        f"{BASE_URL}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM API 错误 {exc.code}: {detail[:500]}") from exc

    try:
        text = data["choices"][0]["message"]["content"].strip()
        if not text:
            raise RuntimeError("LLM API 返回了空文本。")
        return text
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("LLM API 没有返回 chat 文本。") from exc

def main() -> None:
    init_db()
    port = int(os.getenv("PORT", "8765"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Serving on http://0.0.0.0:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
