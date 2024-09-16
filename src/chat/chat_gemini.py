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
    safety_settings: Optional[Dict[str, Any]] = None,
    location: str = "us-central1",
    model_name: str = "gemini-1.5-pro-001"
):
    """Generate text."""
    vertexai.init(project=project_id, location=location)

    if not tools:
        tools = []

    if not safety_settings:
        safety_settings = {
            generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE,
            generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
        }

    # Initialize function calling model
    function_calling_model_instance = GenerativeModel(
        model_name,
        system_instruction=None if not system_instruction else [system_instruction],
        generation_config=GenerationConfig(
            temperature=0.2,
        ),
        safety_settings=safety_settings,
        tools=tools,
        tool_config=ToolConfig(
            function_calling_config=ToolConfig.FunctionCallingConfig(
                mode=ToolConfig.FunctionCallingConfig.Mode.ANY,
                allowed_function_names=["get_diabetes_data_output"],
            ))
    )

    # Initialize output response model
    output_response_model_instance = GenerativeModel(
        model_name,
        system_instruction=None if not system_instruction else [system_instruction],
        generation_config=GenerationConfig(
            temperature=0.2,
        ),
        safety_settings=safety_settings
    )

    if chat_history_id:
        chat_history = get_chat_history(user_id, chat_history_id)
        chat = function_calling_model_instance.start_chat(history=chat_history)
    else:
        chat_history_id, chat_history = str(uuid4()), []
        chat = function_calling_model_instance.start_chat()

    try:
        # Send initial message
        response = chat.send_message(prompt)

        # Initialize tracking variables
        output_text = ""

        break_loop = False
        while True:
            response_parts = []
            processing_parts = response.candidates[0].content.parts
            for part in processing_parts:
                function_call_name = part.function_call.name
                if not function_call_name:
                    # Direct text response
                    output_text = part.text
                    break_loop = True
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

                    instructions = (
                        "Summarize the output answer. Below the output answer include and explain"
                        " each and every query used for the answer."
                        " Always include the output answer and the queries used for the output answer."
                    )
                    api_response = {
                        'queries_used_for_output_answer': str(intermediate_steps),
                        'instructions': instructions,
                        'output_answer': answer}
                    response_part = Part.from_function_response(
                        name=function_call_name,
                        response={"content": api_response},
                    )
                    response_parts.append(response_part)
                else:
                    # Unhandled function call
                    output_text = 'Could not resolve appropriate function and determine an answer.'
                    break

            if break_loop:
                break
            else:
                chat = output_response_model_instance.start_chat(history=chat.history)
                response = chat.send_message(response_parts)
    except Exception as e:
        print(f"Error occurred: {e}\n{traceback.format_exc()}")
        output_text = f"Please try again. An unexpected error occurred."

    # Save chat history
    save_chat_history(user_id, chat_history_id, chat.history)

    return output_text, chat_history_id
