# 모임결정 설문 서버

방 생성, 초대코드 입장, 대기룸, O/X 날짜 투표, 테마 투표, 방장 취합 및 팀원 2 전달 JSON을 제공하는 Flask 웹 앱이다.

## Windows 실행

```powershell
cd "이 폴더 경로"
python -m pip install -r requirements.txt
python app.py
```

실행 후 이 노트북에서는 `http://localhost:5000`으로 접속한다.

같은 Wi-Fi에 연결된 다른 노트북이나 휴대전화에서는 터미널에 표시되는 다음 형태의 주소로 접속한다.

```text
http://192.168.x.x:5000
```

다른 기기에서 접속되지 않으면 Windows 방화벽에서 Python의 개인 네트워크 통신을 허용해야 한다.

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
  "meeting_date": "YYYY-MM-DD",
  "themes": [
    {"name": "테마명", "rank": 1}
  ],
  "users": [
    {"name": "참여자 이름", "address": "출발 주소 또는 역 이름"}
  ]
}
```

인터넷의 서로 다른 장소에서 접속하려면 Render 같은 외부 서버에 배포해야 한다. 로컬 실행 주소는 같은 네트워크 안에서만 사용할 수 있다.
