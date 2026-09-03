# match-diary-data

직관일기 앱이 서버 없이 사용하는 KBO 경기 일정·결과 정적 데이터 저장소입니다.

## 공개 주소

- `https://hyeoz.github.io/match-diary-data/latest.json`
- `https://hyeoz.github.io/match-diary-data/schedules/2026.json`

## 갱신 방식

GitHub Actions가 매일 한국 시간 00:00, 12:00, 18:00에 KBO 공식 일정 페이지의 데이터를 확인합니다. 새 경기나 결과 변경이 있을 때만 JSON을 커밋하며, 스키마·팀·경기장·중복·체크섬 검증에 실패하면 기존 정상 파일과 Pages 배포본을 유지합니다. GitHub의 스케줄 실행 상황에 따라 시작 시각은 잠시 지연될 수 있습니다.

수동 갱신과 검증:

```bash
python3 scripts/fetch_kbo_schedule.py --season 2026
python3 scripts/validate_schedule.py --root .
python3 -m unittest discover -s tests
```

이 저장소에는 공개 경기 정보만 저장합니다. 사용자 기록, 기기 식별자, 사진, API 키, 로그는 포함하지 않습니다.
