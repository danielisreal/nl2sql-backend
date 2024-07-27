import base64
import io
import json
import magic
import os
import time

from dotenv import load_dotenv
from flask import Flask, request, Response, jsonify
from firebase_admin import credentials, auth, initialize_app
from flask_cors import CORS
from google.cloud import firestore
from google.cloud import tasks_v2
from pydub import AudioSegment
from random_word import RandomWords
from vertexai.generative_models import Part
from uuid import uuid4

import prompts.chat_title.prompt as chat_title_prompt
import src.anthropic.generate as anthropic_generate
import src.chat.chat_gemini as perform_chat
from src.utils.utils import clean_text, upload_image_to_gcs


load_dotenv()

app = Flask(__name__)
cors = CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["OPTIONS", "POST", "GET"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"],
        "supports_credentials": True
    }
})

# Initialize Firebase admin
cred = credentials.ApplicationDefault()
initialize_app(cred)


@app.route("/hello-world")
def hello_world():
    """Example Hello World route."""
    name = os.environ.get("NAME", "World")
    return f"Hello {name}!"


@app.route("/test-stream", methods=["POST"])
def test_stream():
    def mock_generate():
        r = RandomWords()
        while True:
            random_word = r.get_random_word()
            if random_word:
                yield random_word + "\n"
            time.sleep(2)

    return Response(mock_generate(), mimetype="text/plain")


@app.route("/chat", methods=['OPTIONS'])
def handle_options():
    response = jsonify({'status': 'OK'})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response


@app.route("/chat", methods=["POST"])
def chat():
    """Chat."""
    # Extract the auth token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'No authorization token provided'}), 401

    try:
        # The token should be in the format "Bearer <token>"
        auth_token = auth_header.split(' ')[1]
        # Verify the token
        decoded_token = auth.verify_id_token(auth_token)
        _ = decoded_token['uid']
    except IndexError:
        return jsonify({'error': 'Invalid authorization header format'}), 401
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid authorization token'}), 401

    if 'json' in request.files:
        json_file = request.files['json']
        json_data = json_file.read().decode('utf-8')
        data = json.loads(json_data) if json_data else {}
    elif 'json' in request.form:
        json_data = request.form.get('json')
        data = json.loads(json_data) if json_data else {}
    else:
        data = request.json or {}

    # Extract text and chat_history_id from the form data
    text = data.get("text")
    if text:
        text = clean_text(text)

    # Processing
    user_id = data.get('user_id', data.get('userId'))
    chat_history_id = data.get("chat_id", data.get("chatId"))
    system_instruction = data.get("system_instruction", data.get("systemInstruction"))

    if 'audio' in request.files:
        audio_file = request.files['audio']
        audio_bytes = audio_file.read()

        # Validate if the input audio bytes are WebM
        mime = magic.Magic(mime=True)
        file_mime_type = mime.from_buffer(audio_bytes)

        if file_mime_type == "video/webm" or file_mime_type == "audio/webm":
            # Load WebM audio bytes into an AudioSegment
            webm_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")

            # Export the audio segment as MP3
            mp3_io = io.BytesIO()
            webm_audio.export(mp3_io, format="mp3")

            # Get the MP3 bytes
            audio_bytes = mp3_io.getvalue()
            audio_mime_type = "audio/mpeg"
        else:
            audio_bytes = None
            audio_mime_type = None
    else:
        # Check if audio is in the JSON payload as base64
        base64_audio = data.get('audio')
        if base64_audio:
            try:
                audio_bytes = base64.b64decode(base64_audio)
                # Detect the MIME type of the decoded audio
                mime = magic.Magic(mime=True)
                audio_mime_type = mime.from_buffer(audio_bytes)

                # If it's WebM, convert to MP3
                if audio_mime_type == "video/webm" or audio_mime_type == "audio/webm":
                    webm_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
                    mp3_io = io.BytesIO()
                    webm_audio.export(mp3_io, format="mp3")
                    audio_bytes = mp3_io.getvalue()
                    audio_mime_type = "audio/mpeg"
            except:
                audio_bytes = None
                audio_mime_type = None
        else:
            audio_bytes = None
            audio_mime_type = None

    # Extract the image file if it exists
    if 'image' in request.files:
        image_file = request.files['image']
        image_bytes = image_file.read()

        # Determine the MIME type of the image
        mime = magic.Magic(mime=True)
        image_mime_type = mime.from_buffer(image_bytes)

        # Process image bytes as needed based on MIME type
        if image_mime_type.startswith("image/"):
            # Upload image to GCS bucket
            image_gcs_path = upload_image_to_gcs(
                user_id,
                chat_history_id,
                image_bytes,
                image_mime_type
            )
        else:
            return jsonify({"error": "Invalid file type for image"}), 400
    else:
        image_mime_type = None
        image_gcs_path = None

    # Generate a unique ID for the message
    # message_id = str(uuid4())

    # Add the message to Firestore immediately
    # db = firestore.Client()
    # chat_ref = db.collection('users').document(user_id).collection('chats').document(chat_history_id)
    # messages_ref = chat_ref.collection('messages')
    # messages_ref.document(message_id).set({
    #     'id': message_id,
    #     'content': text,
    #     'type': 'question',
    #     'timestamp': firestore.SERVER_TIMESTAMP,
    #     'status': 'pending'
    # })

    # Update the chat document
    # chat_ref.update({
    #     'lastMessage': text,
    #     'status': 'processing',
    #     'updatedAt': firestore.SERVER_TIMESTAMP
    # })

    # Create a task for background processing
    client = tasks_v2.CloudTasksClient()
    task = {
        'http_request': {
            'http_method': tasks_v2.HttpMethod.POST,
            'url': 'https://public-chat-hkz47oofua-uc.a.run.app/process-chat',
            'body': json.dumps({
                'text': text,
                'user_id': user_id,
                'chat_history_id': chat_history_id,
                'system_instruction': system_instruction,
                'image_gcs_path': image_gcs_path,
                'image_mime_type': image_mime_type,
                'audio_bytes': audio_bytes,
                'audio_mime_type': audio_mime_type,
                # 'message_id': message_id
            }).encode(),
            'headers': {
                'Content-type': 'application/json'
            }
        }
    }

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "ibx-sql-informatics-project")
    parent = client.queue_path(project_id, "us-central1", 'public-chat')
    client.create_task(request={'parent': parent, 'task': task})

    return jsonify({'status': 'processing'}), 202


@app.route("/process-chat", methods=["POST"])
def process_chat():
    """Process Chat."""
    if 'json' in request.files:
        json_file = request.files['json']
        json_data = json_file.read().decode('utf-8')
        data = json.loads(json_data) if json_data else {}
    elif 'json' in request.form:
        json_data = request.form.get('json')
        data = json.loads(json_data) if json_data else {}
    else:
        data = request.json or {}

    # Get values
    text = data['text']
    user_id = data['user_id']
    chat_history_id = data['chat_history_id']
    system_instruction = data['system_instruction']
    image_gcs_path = data['image_gcs_path']
    image_mime_type = data['image_mime_type']
    audio_bytes = data['audio_bytes']
    audio_mime_type = data['audio_mime_type']
    # message_id = data['message_id']

    # Check for input audio
    if audio_bytes:
        audio_part = Part.from_data(
            data=audio_bytes,
            mime_type=audio_mime_type
        )
    else:
        audio_part = None
    contents = [audio_part] + [text] if audio_part else [text]

    # Check for input image
    if image_gcs_path:
        image_part = Part.from_uri(
            image_gcs_path, image_mime_type
        )
    else:
        image_part = None

    contents = contents + [image_part] if image_part else contents

    output_text, chat_history_id = perform_chat.generate_text(
        prompt=contents,
        system_instruction=system_instruction,
        user_id=user_id,
        chat_history_id=chat_history_id
    )

    # Update Firestore with the generated answer
    db = firestore.Client()
    chat_ref = db.collection('users').document(user_id).collection('chats').document(chat_history_id)
    messages_ref = chat_ref.collection('messages')

    # Add a new message document for the answer
    answer_id = str(uuid4())
    messages_ref.document(answer_id).set({
        'id': answer_id,
        'content': output_text,
        'type': 'answer',
        'status': 'completed',
        'timestamp': firestore.SERVER_TIMESTAMP
    })

    # Update the original question message status
    # message_ref = messages_ref.document(message_id)
    # message_ref.update({
    #     'status': 'completed'
    # })

    # Update the chat document
    chat_ref.update({
        'lastMessage': output_text,
        'status': 'completed',
        'updatedAt': firestore.SERVER_TIMESTAMP
    })

    return jsonify({
        "output_text": output_text,
        "chat_history_id": chat_history_id
    }), 200


@app.route("/get-chat-data", methods=["POST"])
def get_chat_data():
    """Get chat data."""
    # Extract the auth token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'No authorization token provided'}), 401

    try:
        # The token should be in the format "Bearer <token>"
        auth_token = auth_header.split(' ')[1]
        # Verify the token
        decoded_token = auth.verify_id_token(auth_token)
        _ = decoded_token['uid']
    except IndexError:
        return jsonify({'error': 'Invalid authorization header format'}), 401
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid authorization token'}), 401

    if 'json' in request.files:
        json_file = request.files['json']
        json_data = json_file.read().decode('utf-8')
        data = json.loads(json_data) if json_data else {}
    elif 'json' in request.form:
        json_data = request.form.get('json')
        data = json.loads(json_data) if json_data else {}
    else:
        data = request.json or {}

    # Base text
    return jsonify([])


@app.route("/get-chat-title", methods=["POST"])
def get_chat_title():
    """Get chat title."""
    # Extract the auth token from the Authorization header
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'No authorization token provided'}), 401

    try:
        # The token should be in the format "Bearer <token>"
        auth_token = auth_header.split(' ')[1]
        # Verify the token
        decoded_token = auth.verify_id_token(auth_token)
        _ = decoded_token['uid']
    except IndexError:
        return jsonify({'error': 'Invalid authorization header format'}), 401
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid authorization token'}), 401

    if 'json' in request.files:
        json_file = request.files['json']
        json_data = json_file.read().decode('utf-8')
        data = json.loads(json_data) if json_data else {}
    elif 'json' in request.form:
        json_data = request.form.get('json')
        data = json.loads(json_data) if json_data else {}
    else:
        data = request.json or {}

    # Base text
    text = data.get('text')
    if text:
        text = clean_text(text)

    prompt = chat_title_prompt.PROMPT_TEMPLATE.format(input_text=text)
    generated_title = anthropic_generate.generate(prompt=prompt)
    return jsonify({'title': generated_title})


if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
