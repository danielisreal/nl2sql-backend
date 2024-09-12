import os
import traceback
import vertexai
import vertexai.preview.generative_models as generative_models
from vertexai.generative_models import (
    FunctionDeclaration,
    GenerationConfig,
    GenerativeModel,
    Part,
    Tool,
    ToolConfig
)
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.chat.sql_agent import create_database_sql_agent
from src.chat.utils import get_chat_history, save_chat_history


def generate_text(
    prompt,
    system_instruction: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_history_id: Optional[str] = None,
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT"),
    tools: List[Any] = None,
    location: str = "us-central1",
    model_name: str = "gemini-1.5-pro-001"
):
    """Generate text."""
    vertexai.init(project=project_id, location=location)

    if not tools:
        tools = []

    # Initialize Gemini model
    model = GenerativeModel(
        model_name,
        system_instruction=None if not system_instruction else [system_instruction],
        generation_config=GenerationConfig(
            temperature=0.2,
        ),
        safety_settings={
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
        },
        tools=tools,
    )

    if chat_history_id:
        chat_history = get_chat_history(user_id, chat_history_id)
        chat = model.start_chat(history=chat_history)
    else:
        chat_history_id, chat_history = str(uuid4()), []
        chat = model.start_chat()

    try:
        response = chat.send_message(prompt)

        while True:
            function_call_name = response.candidates[0].content.parts[0].function_call.name
            if not function_call_name:
                output_text = response.candidates[0].content.parts[0].text
                break
            elif function_call_name == 'get_diabetes_data_output':
                agent_executor = create_database_sql_agent()
                args = dict(response.candidates[0].content.parts[0].function_call.args)
                output = agent_executor.invoke(f"{system_instruction}\n{args['question']}")
                intermediate_steps = []
                for index, step in enumerate(output['intermediate_steps'][1:]):
                    intermediate_step = step[0].to_json()['kwargs']['tool_input']
                    if intermediate_step not in intermediate_steps:
                        intermediate_steps.append(intermediate_step)

                intermediate_steps = [f"Query {index + 1}:\n" + intermediate_step
                                      for index, intermediate_step in enumerate(intermediate_steps)]

                answer = output['output']
                api_response = {'queries_used_for_answer': str(intermediate_steps), 'answer': answer}
            else:
                output_text = 'Could not resolve appropriate function and determine an answer.'
                break

            response = chat.send_message(
                Part.from_function_response(
                    name=function_call_name,
                    response={
                        "content": api_response,
                    },
                ),
            )
    except Exception as e:
        print(f"Error occurred: {e}\n{traceback.format_exc()}")
        output_text = "Please try again. An unexpected error occurred."

    # Save chat history
    save_chat_history(user_id, chat_history_id, chat.history)

    return output_text, chat_history_id
