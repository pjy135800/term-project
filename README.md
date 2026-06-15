# 야놀까? 약속 정하기 플랫폼

여러 참여자의 날짜, 시간대, 활동 테마와 출발지를 모아 최종 약속 정보를 정하고 장소 추천 서버에 전달하는 Flask 웹 애플리케이션이다. 방 생성부터 투표, 방장 확정, 장소 추천 실행, 전체 참여자의 결과 확인까지 하나의 방 안에서 진행한다.

## 1. 서비스 구성

공개 서비스는 역할이 다른 두 서버와 하나의 데이터베이스로 구성된다.

```text
사용자
  |
  v
Render 입력·투표 서버 (이 저장소)
  - 방 생성과 초대코드 입장
  - 날짜별 아침·점심·저녁 투표
  - 활동 테마 투표와 결과 집계
  - 방장 권한 관리와 조원 추방
  - 최종 날짜·테마 확정
  - 장소 추천 실행과 결과 공유
  |
  | room_code + 서명된 실행 token
  v
Oracle Cloud 장소 추천 서버
  - 주소 및 역 이름 좌표 변환
  - 후보역 선정과 대중교통 시간 계산
  - 주변 테마 장소와 날씨 검색
  - 경로 지도 및 공유 이미지 생성
  |
  | 추천 결과 callback
  v
Render PostgreSQL
  - 방, 참여자, 투표, 최종 선택, 추천 결과 저장
```

이 GitHub 저장소에는 Render에서 실행하는 입력·투표 서버만 포함한다. 장소 추천 코드는 Oracle Cloud 서버와 별도 제출 폴더의 `recommender` 디렉터리에서 관리한다. 두 서버는 HTTP와 JSON으로 통신하므로 서로 다른 Python 버전과 실행 환경에서도 같은 자료 형식만 유지하면 함께 동작한다.

## 2. 주요 기능

### 방과 참여자 관리

- 방장은 모임 이름과 투표 기간을 입력해 방을 만든다.
- 참여자는 6자리 초대코드로 같은 방에 입장한다.
- 브라우저 session에 참여자 token을 저장해 방장과 일반 참여자를 구분한다.
- 방장은 잘못 들어온 참여자를 추방할 수 있다.
- 참여자가 나가거나 추방되면 이전 확정 결과와 장소 추천 결과를 초기화해 오래된 결과가 남지 않게 한다.

### 날짜와 시간대 투표

- 참여자는 각 날짜의 아침, 점심, 저녁을 개별적으로 복수 선택한다.
- 날짜 순위는 그 날짜를 한 번 이상 선택한 사람 수를 기준으로 계산한다.
- 최종 화면에는 날짜 순위와 함께 해당 날짜의 시간대별 득표수를 표시한다.
- 장소 추천에 전달하는 값은 방장이 선택한 최종 날짜 하나이며 시간대별 투표수는 참고 정보로 함께 전달한다.

### 테마 투표

- 음식, 문화/관람, 실내 놀거리, 스포츠/게임 카테고리를 제공한다.
- 카테고리별 검색과 직접 입력을 지원한다.
- 한 참여자가 선택할 수 있는 테마는 최대 5개다.
- 동률을 포함해 투표 결과를 집계하고 방장이 최종 테마를 최대 3개까지 순서대로 확정한다.
- `pc방`, `피시방`, `피씨방`처럼 표기가 다른 값은 동일한 `PC방`으로 정규화한다.

### 장소 추천 연동

- 최종 장소 추천 버튼은 방장에게만 표시된다.
- 입력 서버는 방 코드와 2시간 동안 유효한 서명 token을 추천 서버에 전달한다.
- 추천 서버는 입력 서버의 handoff API에서 최종 날짜, 테마, 참여자 이름과 출발 주소를 조회한다.
- 계산이 끝나면 추천 서버가 callback API로 결과를 저장한다.
- 일반 참여자는 주기적인 상태 조회를 통해 방장과 같은 추천 결과 보기 버튼을 받는다.

## 3. 저장소 구조

```text
.
├── app.py                 # 로컬 실행용 진입점
├── server.py              # Flask route, 투표 집계, DB 및 추천 연동
├── requirements.txt       # Python dependency
├── Procfile               # gunicorn 실행 명령
├── render.yaml            # Render Web Service와 PostgreSQL 설정
├── static/
│   ├── app.js             # 상태 갱신, 검색, 추방 확인 등 browser 동작
│   └── styles.css         # 반응형 UI style
└── templates/
    ├── base.html
    ├── home.html
    ├── room.html
    ├── survey.html
    ├── compile.html
    └── error.html
```

## 4. 실행 환경

- 권장 Python: 3.12.x
- 입력 서버: Flask
- 공개 실행: Render + gunicorn
- 로컬 데이터베이스: SQLite
- 공개 데이터베이스: PostgreSQL

개발용 Mac과 Oracle Cloud 서버의 세부 Python 버전은 다르다. 입력 서버와 추천 서버가 하나의 process에서 library를 공유하지 않고 JSON으로 통신하므로 이 차이는 서비스 동작에 영향을 주지 않는다.

## 5. 로컬 실행

### macOS 또는 Linux

```bash
cd term-project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
RECOMMENDER_URL=http://localhost:8501 python app.py
```

브라우저에서 `http://localhost:5000`으로 접속한다.

### Windows PowerShell

```powershell
cd term-project
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
$env:RECOMMENDER_URL="http://localhost:8501"
py app.py
```

입력 서버만 실행해도 방 생성과 투표 기능은 확인할 수 있다. 최종 장소 추천까지 로컬에서 시험하려면 별도의 추천 서버를 8501번 port에서 함께 실행해야 한다.

## 6. 환경 변수

| 이름 | 용도 | 로컬 기본값 |
|---|---|---|
| `FLASK_SECRET_KEY` | session과 추천 실행 token 서명 | 없으면 `.flask_secret` 자동 생성 |
| `DATABASE_URL` | PostgreSQL 연결 문자열 | 없으면 SQLite 사용 |
| `TEAM_DATABASE_PATH` | 로컬 SQLite 파일 위치 | `team_rooms.db` |
| `RECOMMENDER_URL` | 장소 추천 Streamlit 서버 주소 | `http://localhost:8501` |
| `PORT` | Flask 실행 port | `5000` |

실제 secret과 데이터베이스 접속 문자열은 GitHub에 올리지 않는다. Render에서는 `render.yaml`과 service 환경 변수를 통해 값을 주입한다.

## 7. 데이터 저장

로컬 실행에서는 `team_rooms.db`에 자료를 저장한다. Render에서는 `DATABASE_URL`이 PostgreSQL 형식인지 확인한 뒤 같은 query 흐름을 PostgreSQL에 적용한다.

주요 table은 다음과 같다.

- `rooms`: 방 정보, 투표 상태, 최종 날짜와 테마
- `members`: 참여자 이름, 역할, session token
- `submissions`: 출발 주소, 날짜·시간대 선택, 테마 선택
- `recommendations`: 추천 실행 상태, 결과 JSON, 오류 내용

날짜와 테마 선택은 JSON 문자열로 저장한다. 참여자 삭제 시 관련 submission도 foreign key 설정에 따라 함께 삭제한다.

## 8. 입력 서버와 추천 서버의 JSON 계약

최종 확정 뒤 추천 서버는 다음 endpoint에서 입력 자료를 조회한다.

```http
GET /api/rooms/{room_code}/handoff
```

호환 endpoint도 제공한다.

```http
GET /handoff?room_code={room_code}
```

응답 예시는 다음과 같다.

```json
{
  "meeting_date": "2026-06-20",
  "date_candidates": [
    {
      "date": "2026-06-20",
      "rank": 1,
      "votes": 3,
      "time_slot_votes": {
        "아침": 1,
        "점심": 3,
        "저녁": 2
      }
    }
  ],
  "time_slot_votes": {
    "아침": 1,
    "점심": 3,
    "저녁": 2
  },
  "themes": [
    {"name": "영화관", "rank": 1},
    {"name": "카페", "rank": 2}
  ],
  "users": [
    {"name": "참여자 1", "address": "회기역"},
    {"name": "참여자 2", "address": "서현역"}
  ]
}
```

`meeting_date`는 방장이 최종 선택한 날짜다. `date_candidates`에는 투표 상위 날짜와 날짜별 시간대 득표수가 들어간다. `themes`는 확정 순서가 곧 추천 우선순위이며 별도의 투표수는 전달하지 않는다.

추천 서버의 계산이 끝나면 다음 endpoint로 결과를 돌려보낸다.

```http
POST /api/rooms/{room_code}/recommendation
Content-Type: application/json
```

성공 응답 body:

```json
{
  "run_token": "입력 서버가 발급한 서명 token",
  "status": "completed",
  "result": {
    "status": "success",
    "meeting_station": {},
    "routes": [],
    "recommended_places": []
  }
}
```

실패한 경우 `status`를 `error`로 보내고 `error` 문자열을 포함한다. 입력 서버는 token의 서명, 만료 시간, 방 코드를 확인한 뒤에만 결과를 저장한다.

## 9. 배포와 업데이트

`render.yaml`은 저장소의 `main` branch를 기준으로 입력 서버와 PostgreSQL을 구성한다.

```text
build: pip install -r requirements.txt
start: gunicorn server:app
health check: /health
```

`main`에 새 commit을 push하면 Render의 auto deploy가 시작된다. 배포 후에는 `/health`가 `status: ok`와 사용 중인 데이터베이스 종류를 반환하는지 확인한다.

장소 추천 코드는 이 저장소에서 자동 배포되지 않는다. 추천 코드가 바뀌면 Oracle Cloud의 별도 작업 경로에 파일을 반영하고 Streamlit process를 다시 시작해야 한다.

## 10. 동작 확인 순서

1. 방장이 방을 만들고 초대코드를 공유한다.
2. 참여자들이 출발지, 날짜별 시간대, 테마를 제출한다.
3. 방장이 제출 상태를 확인하고 결과 집계를 시작한다.
4. 방장이 날짜 하나와 순위가 있는 테마를 확정한다.
5. 방장이 최종 장소 추천을 실행한다.
6. 추천 서버가 계산 결과를 입력 서버에 저장한다.
7. 모든 참여자가 동일한 결과 화면을 확인한다.

문제가 발생하면 `/health`, 방 상태 API, `recommendations`의 상태와 각 서버 log를 순서대로 확인한다. 로컬 입력 서버와 공개 Render 서버는 서로 다른 데이터베이스를 사용할 수 있으므로 같은 방 코드가 양쪽에 자동으로 공유되지는 않는다.
