import base64
import os
import vertexai
import vertexai.preview.generative_models as generative_models
from vertexai.generative_models import (
    FunctionDeclaration,
    GenerationConfig,
    GenerativeModel,
    Part,
    Tool,
)
from typing import Optional
from uuid import uuid4

from src.chat.sql_agent import create_database_sql_agent
from src.utils.utils import get_chat_history, save_chat_history

get_diabetes_data_output = FunctionDeclaration(
    name="get_diabetes_data_output",
    description="""\
    Only use this tool if there is explicit reference to a "Diabetes Datamart" dataset. This tool retrieves and analyzes comprehensive diabetes-related data.
    This function accesses a wide range of diabetes management metrics, including but not limited to:

    1. Glycemic control: A1C levels, glucose monitoring data
    2. Medication data: Types of diabetes drugs, insulin usage, adherence metrics (PDC)
    3. Complications: Nephropathy, Neuropathy, Retinopathy, Cardiovascular complications
    4. Healthcare utilization: PCP visits, specialist visits (endocrinology, ophthalmology, podiatry), ER visits, hospitalizations
    5. Preventive care: Eye exams, foot exams, kidney exams
    6. Risk factors: Age, gender, BMI, comorbidities
    7. Treatment programs: Enrollment in diabetes management programs, education sessions
    8. Financial metrics: Medical and pharmacy costs
    9. Longitudinal data: Changes in status, complications, and metrics over time
    10. Demographic and insurance data: Coverage type, location, plan details

    This function can perform various analyses, including but not limited to:
    - Tracking individual patient progress over time
    - Comparing metrics between patients or patient groups
    - Identifying trends in complications or healthcare utilization
    - Assessing the effectiveness of interventions or treatment changes
    - Evaluating adherence to recommended care guidelines
    - Analyzing cost patterns related to diabetes care

    The function can handle complex queries that involve multiple data points and can provide 
    both individual-level and aggregate analyses.\
    """,
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": """\
                A specific question or analysis request related to the diabetes dataset. 
                The question can involve any of the data points mentioned in the function description,
                and can request simple data retrieval, complex analysis, or comparative studies.
                Examples include:
                - 'What is the average A1C level for patients with both nephropathy and retinopathy complications?'
                - 'How does medication adherence correlate with ER visits and hospitalizations over the past year?'
                - 'Compare the healthcare costs for patients enrolled in diabetes management programs versus those who are not.'
                - 'What percentage of patients with an A1C > 9 have had an endocrinologist visit in the last 6 months?'
                - 'Analyze the progression of complications for patients who have been diabetic for more than 5 years.'
                - 'How does the medication adherence of Medicare patients compare to that of commercially insured patients?'\
                """,
            },
        },
        "required": [
            "question",
        ],
    },
)

diabetes_datamart_tool = Tool(
    function_declarations=[
        get_diabetes_data_output
    ],
)


def generate_text(
    prompt,
    system_instruction: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_history_id: Optional[str] = None,
    project_id: str = os.getenv("GOOGLE_CLOUD_PROJECT"),
    location: str = "us-central1",
    model_name: str = "gemini-1.5-pro-001"
):
    """Generate text."""
    vertexai.init(project=project_id, location=location)

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
        tools=[diabetes_datamart_tool],
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
                output = agent_executor.invoke(args['question'])
                intermediate_steps = []
                for index, step in enumerate(output['intermediate_steps'][1:]):
                    intermediate_step = step[0].to_json()['kwargs']['tool_input']
                    if intermediate_step not in intermediate_steps:
                        intermediate_steps.append(intermediate_step)

                intermediate_steps = [f"Query {index + 1}:\n" + intermediate_step
                                      for index, intermediate_step in enumerate(intermediate_steps)]

                answer = output['output']
                answer = f"The answer is {answer}. The queries used to get this answer are:\n{str(intermediate_steps)}"
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
    except:
        output_text = "Please try again. An unexpected error occurred."

    # Save chat history
    save_chat_history(user_id, chat_history_id, chat.history)

    return output_text, chat_history_id
