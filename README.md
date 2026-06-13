# 야놀까? 약속 정하기 플랫폼

방 생성, 초대코드 입장, 대기룸, O/X 날짜 투표, 테마 투표, 방장 취합 및 팀원 2 전달 JSON을 제공하는 Flask 웹 앱이다.

## 현재 공개 서비스 구성

현재 공개 서비스는 입력·투표 서버와 장소 추천 서버를 분리하여 운영한다.

```text
사용자
  ↓
Render 입력·투표 서버
  ├─ 방 생성, 참여자 관리, 날짜·테마 투표
  ├─ 방장의 최종 날짜 선택 및 장소 추천 실행
  └─ PostgreSQL에 방 정보와 추천 결과 저장
        ↓ 장소 추천 요청
Oracle Cloud 추천 서버
  ├─ Streamlit 결과 화면
  ├─ 카카오 Local API를 이용한 주소 변환과 장소 검색
  ├─ ODsay API를 이용한 대중교통 경로와 이동 시간 계산
  ├─ Groq API를 이용한 검색 키워드 보조
  └─ 기상청·Open-Meteo를 이용한 약속일 날씨 조회
        ↓ 계산 결과 전송
Render PostgreSQL
  └─ 같은 방의 모든 참여자에게 동일한 추천 결과 제공
```

각 코드의 저장 및 실행 위치는 다음과 같다.

- GitHub `term-project` 저장소: Flask 입력·투표 코드 저장
- Render: GitHub 코드를 자동 배포하여 입력 화면과 방 관리 기능 실행
- Render PostgreSQL: 참여자, 투표, 최종 선택 및 추천 결과 저장
- Oracle Cloud: 장소 추천 Streamlit 코드와 추천 알고리즘 실행

따라서 이 GitHub 저장소에는 현재 입력·투표 서버 코드가 들어 있으며, 장소 추천 코드는 Oracle Cloud 서버와 별도의 로컬 `recommender` 폴더에서 관리한다. 두 서버는 HTTP API로 입력 정보와 추천 결과를 주고받아 하나의 서비스처럼 동작한다.

## VS Code에서 로컬 실행

Python 3.11 이상이 설치된 환경에서 프로젝트 폴더를 VS Code로 연다.
VS Code 상단 메뉴에서 `Terminal > New Terminal`을 누른 뒤 다음 명령을 순서대로 실행한다.

```powershell
py -m pip install -r requirements.txt
py app.py
```

`py` 명령을 사용할 수 없는 환경에서는 다음과 같이 실행한다.

```powershell
python -m pip install -r requirements.txt
python app.py
```

서버가 실행되면 브라우저에서 다음 주소로 접속한다.

```text
http://localhost:5000
```

종료할 때는 VS Code 터미널을 선택하고 `Ctrl+C`를 누른다.
로컬 실행과 Render 공개 사이트는 서로 다른 서버이므로 방과 설문 데이터도 공유되지 않는다.

## 데이터 저장

- 로컬 실행에서는 방, 참여자, 설문 및 결과가 `team_rooms.db`에 저장된다.
- Render에서는 `DATABASE_URL`을 자동 감지하여 PostgreSQL에 저장한다.
- 로그인 상태를 유지하는 키는 `.flask_secret`에 저장된다.
- 두 파일은 개인 실행 데이터이므로 Git에는 포함하지 않는다.

## Render 무료 배포

`render.yaml`에 무료 Flask 웹 서비스와 무료 PostgreSQL 설정이 포함되어 있다.

1. 이 폴더의 파일을 GitHub 저장소에 올린다.
2. Render에 로그인하고 `New +`에서 `Blueprint`를 선택한다.
3. GitHub 저장소를 연결한다.
4. Render가 `render.yaml`을 인식하면 `Apply`를 누른다.
5. 배포 완료 후 생성된 `https://...onrender.com` 주소를 공유한다.

Render가 자동으로 다음 항목을 설정한다.

- `pip install -r requirements.txt`
- `gunicorn server:app`
- 임의의 `FLASK_SECRET_KEY`
- PostgreSQL 연결 주소인 `DATABASE_URL`

웹 서버가 잠들거나 새 코드가 재배포되어도 설문 데이터는 PostgreSQL에 남는다.
단, Render의 무료 PostgreSQL은 생성 후 30일 동안 제공되므로 발표 일정에 맞춰 생성해야 한다.

## 팀원 2 전달 API

결과 확정 후 다음 주소에서 JSON을 조회한다.

```text
GET /api/rooms/초대코드/handoff
```

호환 주소:

```text
GET /handoff?room_code=초대코드
```

응답 형식:

```json
{
  "meeting_date": "YYYY-MM-DD 또는 null",
  "date_candidates": [
    {"date": "YYYY-MM-DD", "time_slot": "아침/점심/저녁", "rank": 1, "votes": 2}
  ],
  "themes": [
    {"name": "테마명", "rank": 1}
  ],
  "users": [
    {"name": "참여자 이름", "address": "출발 주소 또는 역 이름"}
  ]
}
```

날짜를 확정하지 않은 경우에도 JSON이 생성된다. `meeting_date`는 `null`로 전달하고,
투표로 나온 날짜 후보들은 `date_candidates`에 순위, 시간대, 득표수와 함께 전달한다.

인터넷의 서로 다른 장소에서 접속하려면 Render 같은 외부 서버에 배포해야 한다. 로컬 실행 주소는 같은 네트워크 안에서만 사용할 수 있다.
