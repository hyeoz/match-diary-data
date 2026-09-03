#!/usr/bin/env python3
"""Validate published schedule documents without third-party dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

TEAM_IDS = set(range(1, 11))
STATUSES = {"scheduled", "final", "canceled", "postponed"}
SHA256 = re.compile(r"^[a-f0-9]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^\d{2}:\d{2}$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def iso_datetime(value: Any, field: str) -> None:
    require(isinstance(value, str), f"{field} must be a string")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def validate_season(document: dict[str, Any]) -> None:
    require(document.get("schemaVersion") == 1, "지원하지 않는 schedule schemaVersion")
    season = document.get("season")
    require(isinstance(season, int) and season >= 2024, "season이 올바르지 않음")
    require(isinstance(document.get("dataVersion"), str) and SHA256.match(document["dataVersion"]) is not None, "dataVersion이 올바르지 않음")
    iso_datetime(document.get("generatedAt"), "generatedAt")
    require(document.get("source", {}).get("name") == "KBO 공식 경기 일정", "공식 데이터 출처가 누락됨")

    stadiums = document.get("stadiums")
    games = document.get("games")
    require(isinstance(stadiums, list) and stadiums, "stadiums가 비어 있음")
    require(isinstance(games, list) and len(games) >= 100, "games가 비정상적으로 적음")
    stadium_ids = {item.get("id") for item in stadiums}
    require(len(stadium_ids) == len(stadiums), "중복 경기장 ID")

    game_ids: set[str] = set()
    canonical_games: list[dict[str, Any]] = []
    for game in games:
        game_id = game.get("id")
        require(isinstance(game_id, str) and game_id, "경기 ID 누락")
        require(game_id not in game_ids, f"중복 경기 ID: {game_id}")
        game_ids.add(game_id)
        require(isinstance(game.get("date"), str) and DATE.match(game["date"]) is not None, f"날짜 오류: {game_id}")
        require(game["date"].startswith(f"{season}-"), f"시즌 밖 경기: {game_id}")
        require(isinstance(game.get("time"), str) and TIME.match(game["time"]) is not None, f"시간 오류: {game_id}")
        require(game.get("homeTeamId") in TEAM_IDS and game.get("awayTeamId") in TEAM_IDS, f"팀 ID 오류: {game_id}")
        require(game.get("homeTeamId") != game.get("awayTeamId"), f"동일 팀 경기: {game_id}")
        require(game.get("stadiumId") in stadium_ids, f"경기장 매핑 오류: {game_id}")
        require(game.get("status") in STATUSES, f"상태 오류: {game_id}")
        for score in (game.get("homeScore"), game.get("awayScore")):
            require(score is None or (isinstance(score, int) and score >= 0), f"점수 오류: {game_id}")
        if game.get("status") == "final":
            require(game.get("homeScore") is not None and game.get("awayScore") is not None, f"종료 경기 점수 누락: {game_id}")
        require(isinstance(game.get("memo"), str), f"메모 오류: {game_id}")
        iso_datetime(game.get("updatedAt"), f"updatedAt({game_id})")
        canonical_games.append({key: value for key, value in game.items() if key != "updatedAt"})

    version = hashlib.sha256(json.dumps(canonical_games, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    require(version == document["dataVersion"], "dataVersion 불일치")


def validate_root(root: Path) -> None:
    latest_path = root / "latest.json"
    require(latest_path.is_file(), "latest.json이 없음")
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    require(latest.get("schemaVersion") == 1, "지원하지 않는 latest schemaVersion")
    iso_datetime(latest.get("generatedAt"), "latest.generatedAt")
    seasons = latest.get("seasons")
    require(isinstance(seasons, list) and seasons, "latest.seasons가 비어 있음")

    for item in seasons:
        relative = item.get("path")
        require(isinstance(relative, str) and not relative.startswith("/") and ".." not in Path(relative).parts, "안전하지 않은 season path")
        season_path = root / relative
        require(season_path.is_file(), f"일정 파일 없음: {relative}")
        checksum = hashlib.sha256(season_path.read_bytes()).hexdigest()
        require(checksum == item.get("sha256"), f"체크섬 불일치: {relative}")
        document = json.loads(season_path.read_text(encoding="utf-8"))
        validate_season(document)
        require(item.get("season") == document.get("season"), f"시즌 불일치: {relative}")
        require(item.get("dataVersion") == document.get("dataVersion"), f"버전 불일치: {relative}")
        require(item.get("gameCount") == len(document.get("games", [])), f"경기 수 불일치: {relative}")

    require(any(item.get("season") == latest.get("currentSeason") for item in seasons), "currentSeason 파일이 없음")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    validate_root(args.root)
    print("일정 JSON 검증 완료")


if __name__ == "__main__":
    main()

