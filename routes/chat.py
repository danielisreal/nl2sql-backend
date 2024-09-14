import base64
import io
import json
import magic
import os

from flask import Blueprint, request, jsonify, Response
from firebase_admin import auth
from google.cloud import firestore
from google.cloud import tasks_v2
from pydub import AudioSegment
from vertexai.generative_models import (
    FunctionDeclaration,
    Part,
    Tool
)
from uuid import uuid4

import src.anthropic.generate as anthropic_generate
import src.chat.chat_gemini as perform_chat
import src.routes.utils as endpoint_utils
import src.remote_config.utils as remote_config_utils
from src.chat.utils import clean_text, upload_image_to_gcs


chat_bp = Blueprint('chat', __name__, url_prefix='/chat')


@chat_bp.route("", methods=["POST"])
def chat():
    """Handle chat requests."""
    # Verify the authentication token
    auth_result = endpoint_utils.verify_auth_token(request)
    if isinstance(auth_result, tuple):
        return auth_result

    decoded_token = auth_result
    user_id = decoded_token['uid']

    # Parse JSON data from request
    data = endpoint_utils.parse_json_data(request)

    # Extract and clean text
    text = data.get("text")
    if text:
        text = clean_text(text)

    # Extract other request data
    chat_history_id = data.get("chat_id", data.get("chatId"))
    system_instruction = data.get("system_instruction", data.get("systemInstruction"))

    # Process audio data
    audio_bytes, audio_mime_type = process_audio_data(request, data)

    # Process image data
    image_gcs_path, image_mime_type = process_image_data(request, user_id, chat_history_id)

    # Create a task for background processing
    payload = {
        'text': text,
        'user_id': user_id,
        'chat_history_id': chat_history_id,
        'system_instruction': system_instruction,
        'image_gcs_path': image_gcs_path,
        'image_mime_type': image_mime_type,
        'audio_bytes': audio_bytes,
        'audio_mime_type': audio_mime_type,
    }

    endpoint_utils.create_cloud_task('/chat/task', payload)

    return jsonify({'status': 'processing'}), 202


@chat_bp.route("/task", methods=["POST"])
def task_chat():
    """Task: Process chat in the background."""
    data = endpoint_utils.parse_json_data(request)

    # Extract data from the request
    text = data['text']
    user_id = data['user_id']
    chat_history_id = data['chat_history_id']
    image_gcs_path = data['image_gcs_path']
    image_mime_type = data['image_mime_type']
    audio_bytes = data['audio_bytes']
    audio_mime_type = data['audio_mime_type']

    # Prepare content for chat generation
    contents = prepare_chat_contents(text, audio_bytes, audio_mime_type, image_gcs_path, image_mime_type)

    # Fetch system instruction
    config = remote_config_utils.get_remote_config_value("Prompts", "sqlAgentSystemInstruction")
    if not config:
        return Response("Configuration not found", status=404)

    file_name = config['fileName']
    system_instruction = remote_config_utils.get_gcs_prompt(file_name)

    # Define diabetes datamart tool
    # -- SQL Agent Function Description
    config = remote_config_utils.get_remote_config_value("Prompts", "sqlAgentFunctionDescription")
    if not config:
        return Response("Configuration not found", status=404)

    file_name = config['fileName']
    sql_agent_function_description = remote_config_utils.get_gcs_prompt(file_name)

    # -- SQL Agent Function Parameters
    config = remote_config_utils.get_remote_config_value("Prompts", "sqlAgentFunctionParameters")
    if not config:
        return Response("Configuration not found", status=404)

    file_name = config['fileName']
    sql_agent_function_parameters = remote_config_utils.get_gcs_prompt(file_name)
    sql_agent_function_parameters = json.loads(sql_agent_function_parameters)

    get_diabetes_data_output = FunctionDeclaration(
        name="get_diabetes_data_output",
        description=sql_agent_function_description,
        parameters=sql_agent_function_parameters,
    )

    diabetes_datamart_tool = Tool(
        function_declarations=[
            get_diabetes_data_output
        ],
    )

    # Generate chat response
    output_text, chat_history_id = perform_chat.generate_text(
        prompt=contents,
        system_instruction=system_instruction,
        user_id=user_id,
        chat_history_id=chat_history_id,
        tools=[diabetes_datamart_tool],
    )

    # Update Firestore with the generated answer
    update_firestore(user_id, chat_history_id, output_text)

    return jsonify({
        "output_text": output_text,
        "chat_history_id": chat_history_id
    }), 200


def process_audio_data(request, data):
    """Process audio data from the request."""
    if 'audio' in request.files:
        audio_file = request.files['audio']
        audio_bytes = audio_file.read()
        mime = magic.Magic(mime=True)
        file_mime_type = mime.from_buffer(audio_bytes)

        if file_mime_type in ["video/webm", "audio/webm"]:
            webm_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
            mp3_io = io.BytesIO()
            webm_audio.export(mp3_io, format="mp3")
            return mp3_io.getvalue(), "audio/mpeg"
        else:
            return None, None
    elif 'audio' in data:
        try:
            audio_bytes = base64.b64decode(data['audio'])
            mime = magic.Magic(mime=True)
            audio_mime_type = mime.from_buffer(audio_bytes)

            if audio_mime_type in ["video/webm", "audio/webm"]:
                webm_audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format="webm")
                mp3_io = io.BytesIO()
                webm_audio.export(mp3_io, format="mp3")
                return mp3_io.getvalue(), "audio/mpeg"
            return audio_bytes, audio_mime_type
        except:
            return None, None
    return None, None


def process_image_data(request, user_id, chat_history_id):
    """Process image data from the request."""
    if 'image' in request.files:
        image_file = request.files['image']
        image_bytes = image_file.read()
        mime = magic.Magic(mime=True)
        image_mime_type = mime.from_buffer(image_bytes)

        if image_mime_type.startswith("image/"):
            image_gcs_path = upload_image_to_gcs(
                user_id,
                chat_history_id,
                image_bytes,
                image_mime_type
            )
            return image_gcs_path, image_mime_type
    return None, None


def prepare_chat_contents(text, audio_bytes, audio_mime_type, image_gcs_path, image_mime_type):
    """Prepare contents for chat generation."""
    contents = []

    if audio_bytes:
        audio_part = Part.from_data(data=audio_bytes, mime_type=audio_mime_type)
        contents.append(audio_part)

    contents.append(text)

    if image_gcs_path:
        image_part = Part.from_uri(image_gcs_path, image_mime_type)
        contents.append(image_part)

    return contents


def update_firestore(user_id, chat_history_id, output_text):
    """Update Firestore with the generated answer."""
    db = firestore.Client()
    chat_ref = db.collection('users').document(user_id).collection('chats').document(chat_history_id)
    messages_ref = chat_ref.collection('messages')

    answer_id = str(uuid4())
    messages_ref.document(answer_id).set({
        'id': answer_id,
        'content': output_text,
        'type': 'answer',
        'status': 'completed',
        'timestamp': firestore.SERVER_TIMESTAMP
    })

    chat_ref.update({
        'lastMessage': output_text,
        'status': 'completed',
        'updatedAt': firestore.SERVER_TIMESTAMP
    })


@chat_bp.route("/title", methods=["POST"])
def get_chat_title():
    """Generate a title for the chat."""
    # Verify the authentication token
    auth_result = endpoint_utils.verify_auth_token(request)
    if isinstance(auth_result, tuple):
        return auth_result

    decoded_token = auth_result
    _ = decoded_token['uid']

    # Parse JSON data from request
    data = endpoint_utils.parse_json_data(request)

    # Extract and clean text
    text = data.get('text')
    if text:
        text = clean_text(text)

    # Prompt
    # Fetch configuration from Remote Config
    config = remote_config_utils.get_remote_config_value("Prompts", "generateChatTitle")
    if not config:
        return Response("Configuration not found", status=404)

    file_name = config['fileName']

    # Fetch prompt from GCS
    prompt = remote_config_utils.get_gcs_prompt(file_name)

    # Generate chat title
    prompt = prompt.format(input_text=text)
    generated_title = anthropic_generate.generate(prompt=prompt)
    return jsonify({'title': generated_title})
