#!/usr/bin/env python3
"""Fetch KBO schedule rows and publish a stable season JSON document."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ENDPOINT = "https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList"
SOURCE_PAGE = "https://www.koreabaseball.com/Schedule/Schedule.aspx"
SCHEMA_VERSION = 1

TEAM_IDS = {
    "SSG": 1,
    "LG": 2,
    "키움": 3,
    "KT": 4,
    "KIA": 5,
    "NC": 6,
    "삼성": 7,
    "롯데": 8,
    "두산": 9,
    "한화": 10,
}

STADIUMS = {
    "문학": ("incheon", "인천SSG랜더스필드", "랜더스필드", 37.4369, 126.6933),
    "인천": ("incheon", "인천SSG랜더스필드", "랜더스필드", 37.4369, 126.6933),
    "잠실": ("jamsil", "잠실야구장", "잠실", 37.5122, 127.0719),
    "수원": ("suwon", "수원KT위즈파크", "수원", 37.2998, 127.0097),
    "대전": ("daejeon", "대전한화생명볼파크", "대전", 36.3171, 127.4292),
    "대전(신)": ("daejeon", "대전한화생명볼파크", "대전", 36.3171, 127.4292),
    "사직": ("sajik", "사직야구장", "사직", 35.1940, 129.0615),
    "고척": ("gocheok", "고척스카이돔", "고척", 37.4982, 126.8671),
    "창원": ("changwon", "창원NC파크", "창원", 35.2225, 128.5823),
    "광주": ("gwangju", "광주기아챔피언스필드", "광주", 35.1681, 126.8891),
    "대구": ("daegu", "대구삼성라이온즈파크", "대구", 35.8412, 128.6812),
    "포항": ("pohang", "포항야구장", "포항", None, None),
    "청주": ("cheongju", "청주야구장", "청주", None, None),
    "울산": ("ulsan", "울산문수야구장", "울산", None, None),
}

SERIES = (
    ("regular", "0,9,6", range(3, 12)),
    ("postseason", "3,4,5,7", range(9, 12)),
)


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = data.strip()
        if value:
            self.parts.append(value)


def html_texts(value: str) -> list[str]:
    parser = _TextParser()
    parser.feed(value or "")
    return parser.parts


def parse_date(value: str, season: int) -> str:
    match = re.match(r"^(\d{2})\.(\d{2})", value.strip())
    if not match:
        raise ValueError(f"날짜 형식을 해석할 수 없습니다: {value!r}")
    return f"{season}-{match.group(1)}-{match.group(2)}"


def parse_time(value: str) -> str:
    text = "".join(html_texts(value))
    match = re.search(r"(\d{1,2}):(\d{2})", text)
    if not match:
        raise ValueError(f"경기 시간을 해석할 수 없습니다: {value!r}")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def official_game_id(cells: list[dict[str, Any]]) -> str | None:
    for cell in cells:
        match = re.search(r"[?&]gameId=([A-Za-z0-9]+)", cell.get("Text", ""))
        if match:
            return match.group(1)
    return None


def status_for(memo: str, home_score: int | None, away_score: int | None) -> str:
    if any(word in memo for word in ("취소", "노게임")):
        return "canceled"
    if any(word in memo for word in ("연기", "순연")):
        return "postponed"
    if home_score is not None and away_score is not None:
        return "final"
    return "scheduled"


def parse_rows(payload: dict[str, Any], season: int, series: str) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    current_date: str | None = None
    fallback_counts: dict[str, int] = {}

    for raw in payload.get("rows", []):
        cells = raw.get("row", [])
        if not cells:
            continue
        is_day_row = cells[0].get("Class") == "day"
        if is_day_row:
            current_date = parse_date(cells[0].get("Text", ""), season)
        if not current_date:
            continue

        time_index = 1 if is_day_row else 0
        play_index = 2 if is_day_row else 1
        stadium_index = 7 if is_day_row else 6
        memo_index = 8 if is_day_row else 7
        if len(cells) <= max(time_index, play_index, stadium_index):
            continue

        play = html_texts(cells[play_index].get("Text", ""))
        if len(play) < 3 or play[0] not in TEAM_IDS or play[-1] not in TEAM_IDS:
            continue

        away_name, home_name = play[0], play[-1]
        numeric = [int(value) for value in play[1:-1] if value.isdigit()]
        away_score = numeric[0] if len(numeric) >= 2 else None
        home_score = numeric[-1] if len(numeric) >= 2 else None
        stadium_name = cells[stadium_index].get("Text", "").strip()
        if stadium_name not in STADIUMS:
            raise ValueError(f"등록되지 않은 경기장: {stadium_name!r}")
        stadium_id = STADIUMS[stadium_name][0]
        memo = ""
        if len(cells) > memo_index:
            memo = " ".join(html_texts(cells[memo_index].get("Text", ""))).strip()
        if memo == "-":
            memo = ""
        time = parse_time(cells[time_index].get("Text", ""))
        game_id = official_game_id(cells)
        if not game_id:
            base = f"{current_date}-{away_name}-{home_name}-{stadium_id}-{time}-{series}"
            fallback_counts[base] = fallback_counts.get(base, 0) + 1
            game_id = f"kbo-{base}-{fallback_counts[base]}"

        games.append(
            {
                "id": game_id,
                "date": current_date,
                "time": time,
                "homeTeamId": TEAM_IDS[home_name],
                "awayTeamId": TEAM_IDS[away_name],
                "stadiumId": stadium_id,
                "status": status_for(memo, home_score, away_score),
                "homeScore": home_score,
                "awayScore": away_score,
                "memo": memo,
            }
        )
    return games


def fetch_month(season: int, month: int, series_ids: str) -> dict[str, Any]:
    data = f"leId=1&srIdList={series_ids.replace(',', '%2C')}&seasonId={season}&gameMonth={month:02d}&teamId="
    result = subprocess.run(
        [
            "curl",
            "--fail-with-body",
            "--silent",
            "--show-error",
            "--max-time",
            "30",
            "--retry",
            "2",
            "--user-agent",
            "Mozilla/5.0 (compatible; MatchDiarySchedule/1.0)",
            "--referer",
            SOURCE_PAGE,
            "--header",
            "X-Requested-With: XMLHttpRequest",
            "--header",
            "Content-Type: application/x-www-form-urlencoded; charset=UTF-8",
            "--header",
            "Accept: application/json, text/javascript, */*; q=0.01",
            "--data",
            data,
            ENDPOINT,
        ],
        check=True,
        capture_output=True,
    )
    return json.loads(result.stdout.decode("utf-8-sig"))


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def without_updated_at(game: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in game.items() if key != "updatedAt"}


def stadium_documents(now: str, used_ids: set[str]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for value in STADIUMS.values():
        stadium_id, name, short_name, latitude, longitude = value
        if stadium_id not in used_ids:
            continue
        unique[stadium_id] = {
            "id": stadium_id,
            "name": name,
            "shortName": short_name,
            "latitude": latitude,
            "longitude": longitude,
            "updatedAt": now,
        }
    return [unique[key] for key in sorted(unique)]


def write_if_changed(root: Path, season: int, fetched: list[dict[str, Any]], allow_large_change: bool) -> bool:
    schedule_path = root / "schedules" / f"{season}.json"
    previous: dict[str, Any] | None = None
    if schedule_path.exists():
        previous = json.loads(schedule_path.read_text(encoding="utf-8"))
        previous_count = len(previous.get("games", []))
        if not allow_large_change and previous_count >= 100 and len(fetched) < int(previous_count * 0.85):
            raise ValueError(f"경기 수가 비정상적으로 감소했습니다: {previous_count} -> {len(fetched)}")
    elif len(fetched) < 100:
        raise ValueError(f"첫 일정 파일의 경기 수가 너무 적습니다: {len(fetched)}")

    deduplicated: dict[str, dict[str, Any]] = {}
    for game in fetched:
        deduplicated[game["id"]] = game
    games = sorted(deduplicated.values(), key=lambda item: (item["date"], item["time"], item["id"]))

    data_version = hashlib.sha256(canonical_json(games)).hexdigest()
    if previous and previous.get("dataVersion") == data_version:
        print(f"{season} 일정 변경 없음 ({len(games)}경기)")
        return False

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    previous_games = {game["id"]: game for game in (previous or {}).get("games", [])}
    for game in games:
        old = previous_games.get(game["id"])
        game["updatedAt"] = (
            old.get("updatedAt", now)
            if old and without_updated_at(old) == game
            else now
        )

    document = {
        "schemaVersion": SCHEMA_VERSION,
        "season": season,
        "dataVersion": data_version,
        "generatedAt": now,
        "source": {"name": "KBO 공식 경기 일정", "url": SOURCE_PAGE},
        "stadiums": stadium_documents(now, {game["stadiumId"] for game in games}),
        "games": games,
    }
    schedule_path.parent.mkdir(parents=True, exist_ok=True)
    schedule_path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checksum = hashlib.sha256(schedule_path.read_bytes()).hexdigest()
    latest = {
        "schemaVersion": SCHEMA_VERSION,
        "currentSeason": season,
        "generatedAt": now,
        "seasons": [
            {
                "season": season,
                "path": f"schedules/{season}.json",
                "sha256": checksum,
                "dataVersion": data_version,
                "gameCount": len(games),
                "generatedAt": now,
            }
        ],
    }
    (root / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{season} 일정 갱신 완료 ({len(games)}경기, {data_version[:12]})")
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=datetime.now().year)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--allow-large-change", action="store_true")
    args = parser.parse_args()

    fetched: list[dict[str, Any]] = []
    for series, series_ids, months in SERIES:
        for month in months:
            fetched.extend(parse_rows(fetch_month(args.season, month, series_ids), args.season, series))
    write_if_changed(args.root, args.season, fetched, args.allow_large_change)


if __name__ == "__main__":
    main()

