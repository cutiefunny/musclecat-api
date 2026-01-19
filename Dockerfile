# 1. 베이스 이미지 설정 (Python 3.9 슬림 버전 사용)
FROM python:3.9-slim

# 2. 작업 디렉토리 설정
WORKDIR /app

# 3. 의존성 설치
# 캐시 효율을 위해 requirements.txt를 먼저 복사하여 설치합니다.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 소스 코드 복사
COPY . .

# 5. 포트 노출 (컨테이너 내부 포트)
EXPOSE 8001

# 6. 서버 실행 명령어
# 외부 접속을 허용하기 위해 host를 0.0.0.0으로 설정합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]