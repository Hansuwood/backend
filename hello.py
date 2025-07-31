from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from openai import OpenAI
import os 
import logging
from datetime import datetime
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# ASSISTANT_ID를 환경변수에서 불러오기
ASSISTANT_ID: str = os.environ.get("ASSISTANT_ID")  # type: ignore
if not ASSISTANT_ID:
    raise ValueError("ASSISTANT_ID 환경변수가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, supports_credentials=True)

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


@app.route('/')
def home():
    return 'Home!'

@app.route('/hello')
def hello():
    return 'Hello World!'

@app.route('/sendMessage', methods=['POST', 'GET'])
def sendMessage():
    if request.method == 'POST':
        try:
            data = request.get_json()
            message = data.get('message', '')
            # 쿠키에서 thread_id 가져오기
            thread_id = request.cookies.get('thread_id')
            new_thread_created = False
            # 로그 출력
            logger.info("=" * 50)
            logger.info("📨 메시지 전송 요청 받음")
            logger.info(f"📝 사용자 메시지: {message}")
            logger.info(f"⏰ 요청 시간: {datetime.now()}")
            logger.info("=" * 50)

            if not thread_id:
                # 1. Thread를 새로 생성
                thread = client.beta.threads.create()
                thread_id = thread.id
                new_thread_created = True
                logger.info(f"🧵 새 Thread 생성: {thread_id}")
            else:
                logger.info(f"🔄 기존 Thread 사용: {thread_id}")

            # 2. Thread에 메시지 추가
            client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message
            )
            logger.info("💬 메시지 Thread에 추가 완료")

            # 3. Run 생성
            run = client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=ASSISTANT_ID
            )
            run_id = run.id
            logger.info(f"🏃‍♂️ Run 생성: {run_id}")

            # 4. Run 상태 폴링 (최대 30초 대기)
            import time
            timeout = 30
            poll_interval = 1
            waited = 0
            while waited < timeout:
                run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
                if run_status.status == "completed":
                    logger.info("✅ Run 완료")
                    break
                elif run_status.status in ["failed", "cancelled", "expired"]:
                    logger.error(f"❌ Run 실패: {run_status.status}")
                    resp = make_response(jsonify({
                        'status': 'error',
                        'message': f'Assistant Run 실패: {run_status.status}'
                    }), 500)
                    if new_thread_created:
                        resp.set_cookie('thread_id', thread_id, max_age=60*60*24*7)
                    return resp
                time.sleep(poll_interval)
                waited += poll_interval
            else:
                logger.error("❌ Run 대기 시간 초과")
                resp = make_response(jsonify({
                    'status': 'error',
                    'message': 'Assistant Run 대기 시간 초과'
                }), 500)
                if new_thread_created:
                    resp.set_cookie('thread_id', thread_id, max_age=60*60*24*7)
                return resp

            # 5. 메시지 목록에서 Assistant 응답 추출
            messages = client.beta.threads.messages.list(thread_id=thread_id)
            ai_response = ""
            for msg in reversed(messages.data):
                if msg.role == "assistant":
                    text_blocks = []
                    for content in msg.content:
                        if hasattr(content, "type") and content.type == "text" and hasattr(content, "text") and hasattr(content.text, "value"):
                            text_blocks.append(content.text.value)
                    if text_blocks:
                        ai_response = "\n".join(text_blocks)
                        break
            if not ai_response:
                logger.error("❌ Assistant 응답 없음")
                resp = make_response(jsonify({
                    'status': 'error',
                    'message': 'Assistant 응답 없음'
                }), 500)
                if new_thread_created:
                    resp.set_cookie('thread_id', thread_id, max_age=60*60*24*7)
                return resp

            # 파일 인용 표기(예: 【4:0†이력서.txt】)와 그 뒤 마침표까지 제거
            import re
            ai_response = re.sub(r"【\d+:\d+†.+?】\.?", "", ai_response, flags=re.UNICODE).strip()

            logger.info(f"✅ Assistant 응답: {ai_response}")
            logger.info("=" * 50)

            resp = make_response(jsonify({
                'status': 'success',
                'ai_response': ai_response
            }))
            if new_thread_created:
                resp.set_cookie('thread_id', thread_id, max_age=60*60*24*7)  # 7일 유지
            return resp
        except Exception as e:
            logger.error(f"❌ 오류 발생: {str(e)}")
            logger.error("=" * 50)
            return jsonify({
                'status': 'error',
                'message': f'OpenAI 오류: {str(e)}'
            }), 500

    elif request.method == 'GET':
        return jsonify({'status': 'ready', 'message': '메시지 전송 준비됨'})

    return jsonify({'status': 'error', 'message': '지원하지 않는 메서드입니다'}), 405

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001) 