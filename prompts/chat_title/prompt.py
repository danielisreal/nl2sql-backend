import os

# Define the paths to the system instruction and prompt template files
base_path = os.path.dirname(__file__)
prompt_template_path = os.path.join(base_path, 'prompt_template.txt')

# Read the content of the prompt template
with open(prompt_template_path, 'r') as file:
    PROMPT_TEMPLATE = file.read()
