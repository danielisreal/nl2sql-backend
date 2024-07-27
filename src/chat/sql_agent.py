import os
import vertexai

from langchain.agents import create_sql_agent
from langchain.agents.agent_toolkits import SQLDatabaseToolkit
from langchain.sql_database import SQLDatabase
from langchain_google_vertexai import VertexAI
from langchain_google_vertexai.model_garden import ChatAnthropicVertex
from typing import Optional


def get_langchain_llm(
    project_id: Optional[str] = os.getenv("GOOGLE_CLOUD_PROJECT", "ibx-sql-informatics-project"),
    location: Optional[str] = "us-central1",
    model_name: str = "claude-3-5-sonnet@20240620",
    max_output_tokens: int = 4096,
    temperature: float = 0.2,
    top_p: float = 0.8,
    top_k: int = 40
):
    """Get LangChain LLM."""
    vertexai.init(project=project_id, location=location)

    if model_name.lower().startswith('claude'):
        llm = ChatAnthropicVertex(
            project=project_id,
            location="us-east5",
            model_name=model_name,
            max_output_tokens=4096
        )
    else:
        llm = VertexAI(
          model_name=model_name,
          max_output_tokens=max_output_tokens,
          temperature=temperature,
          top_p=top_p,
          top_k=top_k,
        )

    return llm


def create_database_sql_agent():
    """Create Database SQL Agent."""

    # TODO: Remove hardcoding of sqlalchemy_url
    project_id = 'ibx-sql-informatics-project'
    dataset_id = 'mock_diabetes_datamart'
    sqlalchemy_url = f'bigquery://{project_id}/{dataset_id}'
    db = SQLDatabase.from_uri(sqlalchemy_url)

    # TODO: Remove hardcoding of langchain llm
    llm = get_langchain_llm()

    toolkit = SQLDatabaseToolkit(db=db, llm=llm)
    agent_executor = create_sql_agent(
        llm=llm,
        toolkit=toolkit,
        verbose=False,
        top_k=100000,
        agent_executor_kwargs={"return_intermediate_steps": True}
    )
    return agent_executor
