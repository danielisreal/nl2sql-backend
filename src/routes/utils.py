import json
import os
import random
from google.cloud import tasks_v2
from flask import jsonify
from firebase_admin import auth


def verify_auth_token(request):
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return jsonify({'error': 'No authorization token provided'}), 401

    try:
        auth_token = auth_header.split(' ')[1]
        return auth.verify_id_token(auth_token)
    except IndexError:
        return jsonify({'error': 'Invalid authorization header format'}), 401
    except auth.InvalidIdTokenError:
        return jsonify({'error': 'Invalid authorization token'}), 401


def parse_json_data(request):
    """Parse JSON data from the request."""
    if 'json' in request.files:
        json_file = request.files['json']
        json_data = json_file.read().decode('utf-8')
        return json.loads(json_data) if json_data else {}
    elif 'json' in request.form:
        json_data = request.form.get('json')
        return json.loads(json_data) if json_data else {}
    else:
        return request.json or {}


def create_cloud_task(url, payload, **kwargs):
    client = tasks_v2.CloudTasksClient()

    # Determine project ID
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

    # Determine project region
    project_region = os.getenv("GOOGLE_CLOUD_REGION")

    # Determine project number
    project_number = os.getenv("GOOGLE_CLOUD_PROJECT_NUMBER")

    # Determine queue
    queue = os.getenv("CLOUD_TASKS_QUEUE")

    # Determine queue region
    queue_region = os.getenv("CLOUD_TASKS_QUEUE_REGION")

    # Determine Cloud Run instance name
    instance_name = os.getenv("K_SERVICE")

    parent = client.queue_path(project_id, queue_region, queue)

    # Add any additional kwargs to the task payload
    task_payload = {**payload, **kwargs}

    # Determine instance url
    instance_url = f'https://{instance_name}-{project_number}.{project_region}.run.app{url}'

    task = {
        'http_request': {
            'http_method': tasks_v2.HttpMethod.POST,
            'url': instance_url,
            'body': json.dumps(task_payload).encode(),
            'headers': {'Content-Type': 'application/json'}
        }
    }

    response = client.create_task(request={'parent': parent, 'task': task})
    return response.name
