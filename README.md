# NL2SQL Backend

This repository contains the backend implementation for the NL2SQL project. It is a Flask-based application designed to handle chat interactions, process audio and image data, and integrate with various Google Cloud services. Below is an overview of the workspace structure and the purpose of each file or directory.

---

## Project Structure

### Root Files
- **`main.py`**: The entry point of the Flask application. It initializes the app, sets up routes, and configures Firebase and CORS.
- **`requirements.txt`**: Lists all the Python dependencies required for the project.
- **`Dockerfile`**: Defines the Docker image for the application, including dependencies and environment variables.
- **`Procfile`**: Specifies the command to run the application in a production environment (e.g., Heroku).
- **`.gitignore`**: Specifies files and directories to be ignored by Git.

---

### Directories

#### `prompts/`
- **`__init__.py`**: Placeholder for the prompts module.

#### `routes/`
- **`__init__.py`**: Placeholder for the routes module.
- **`chat.py`**: Contains the Flask blueprint for handling chat-related routes, including chat processing, task handling, and title generation.

#### `src/`
- **`__init__.py`**: Placeholder for the `src` module.

##### `src/anthropic/`
- **`__init__.py`**: Placeholder for the `anthropic` module.
- **`generate.py`**: Provides functions to generate and stream responses using Anthropic's Claude model.

##### `src/chat/`
- **`__init__.py`**: Placeholder for the `chat` module.
- **`chat_gemini.py`**: Implements chat generation using Vertex AI's generative models.
- **`sql_agent.py`**: Creates a SQL agent for querying BigQuery using LangChain.
- **`utils.py`**: Utility functions for chat processing, including cleaning text, managing chat history, and uploading images to Google Cloud Storage.

##### `src/remote_config/`
- **`__init__.py`**: Placeholder for the `remote_config` module.
- **`utils.py`**: Provides utilities for fetching and caching Firebase Remote Config values and Google Cloud Storage prompts.

##### `src/routes/`
- **`__init__.py`**: Placeholder for the `routes` module.
- **`utils.py`**: Contains helper functions for verifying authentication tokens, parsing JSON data, and creating Cloud Tasks.

---

## Key Features
- **Chat Processing**: Handles user chat requests, processes audio and image data, and generates responses using Vertex AI and Anthropic models.
- **Google Cloud Integration**: Utilizes services like Firestore, Cloud Storage, Cloud Tasks, and BigQuery.
- **Extensibility**: Modular design with separate directories for routes, utilities, and external integrations.
- **Dockerized Deployment**: Includes a `Dockerfile` for containerized deployment.

---

## Getting Started

### Prerequisites
- Python 3.11
- Docker (optional for containerized deployment)
- Google Cloud SDK (for local development and deployment)

### Installation
1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd ibx-sql-informatics-backend
   ```
2. Install dependencies:
```bash
pip install -r requirements.txt
```
### Running Locally
Start the Flask application:
```bash
python [main.py](http://_vscodecontentref_/0)
```

### Docker Deployment
Build and run the Docker container:
```bash
docker build -t ibx-sql-informatics-backend .
docker run -p 8080:8080 ibx-sql-informatics-backend
```

### Environment Variables
The application relies on the following environment variables:

- BIGQUERY_DATASET
CLOUD_TASKS_QUEUE
CLOUD_TASKS_QUEUE_REGION
GOOGLE_CLOUD_PROJECT
GOOGLE_CLOUD_PROJECT_NUMBER
GOOGLE_CLOUD_REGION
GOOGLE_CLOUD_BUCKET
Contributing
Feel free to submit issues or pull requests to improve the project.

### Contributing
Feel free to submit issues or pull requests to improve the project.

### License
This project is licensed under the MIT License. ```