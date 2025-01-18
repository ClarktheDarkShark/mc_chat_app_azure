"""
agent_langchain.py
------------------

A standalone module that builds an AI agent using LangChain.
The agent is equipped with a set of tools (functions) to perform various actions 
(e.g. sending an email, creating a calendar invite) and uses the LLM to determine which tool 
to use and with what parameters when given a natural language command.

Usage in your chat.py:
  from agent_langchain import execute_agent_command
  user_command = "Send an email to alice@example.com with subject 'Meeting' and body 'Let’s meet at 3pm tomorrow.'"
  result = execute_agent_command(user_command)
  print("Agent result:", result)
"""

import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta

from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain.chat_models import ChatOpenAI

# ------------------------------------
# Tool Function Definitions
# ------------------------------------

def send_email(to: str, subject: str, body: str) -> str:
    """
    Sends an email. This is a placeholder implementation.
    In production, integrate with your email service via SMTP or an API.
    Required environment variables (if using a real email service):
      EMAIL_FROM, SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD.
    """
    # For demonstration, we simply return a success message.
    # Uncomment and configure the following code to actually send an email.
    """
    from_addr = os.getenv("EMAIL_FROM", "your_email@example.com")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to

    try:
        smtp_server = os.getenv("SMTP_SERVER", "smtp.example.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_username = os.getenv("SMTP_USERNAME", "your_username")
        smtp_password = os.getenv("SMTP_PASSWORD", "your_password")
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(from_addr, [to], msg.as_string())
        server.quit()
        return f"Email sent successfully to {to}."
    except Exception as e:
        return f"Error sending email: {e}"
    """
    return f"(Simulation) Email sent successfully to {to} with subject '{subject}'."

def create_calendar_invite(title: str, start_time: str, end_time: str, location: str, attendees: str) -> str:
    """
    Creates a calendar invite. This is a simulated implementation.
    In production, integrate with a calendar API (like Google Calendar).
    
    Note: 'attendees' should be a comma-separated string of email addresses.
    """
    return (f"(Simulation) Calendar invite '{title}' created from {start_time} to {end_time} "
            f"at {location} for attendees: {attendees}.")

# ------------------------------------
# Register Tools with LangChain
# ------------------------------------

# Create LangChain Tool objects. The 'func' key specifies the function to call.
send_email_tool = Tool(
    name="send_email",
    func=send_email,
    description=(
        "Sends an email. "
        "Input should be a JSON string with keys: 'to' (string), 'subject' (string), and 'body' (string)."
    )
)

create_calendar_invite_tool = Tool(
    name="create_calendar_invite",
    func=create_calendar_invite,
    description=(
        "Creates a calendar invite. "
        "Input should be a JSON string with keys: 'title' (string), 'start_time' (ISO 8601 string), "
        "'end_time' (ISO 8601 string), 'location' (string), and 'attendees' (a comma-separated string of emails)."
    )
)

available_tools = [send_email_tool, create_calendar_invite_tool]

# ------------------------------------
# Initialize the LangChain Agent
# ------------------------------------

# Create a ChatOpenAI LLM. Adjust temperature for more deterministic output.
llm = ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo")

# Initialize an agent using the zero-shot React (action) agent type.
agent = initialize_agent(
    tools=available_tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# ------------------------------------
# Public Function to Execute a Command
# ------------------------------------

def execute_agent_command(user_command: str) -> str:
    """
    Given a natural language user command, uses the LangChain agent to decide which tool to call,
    with what parameters, executes that tool, and returns the result.
    
    Example user commands:
      - "Send an email to alice@example.com with subject 'Meeting' and body 'Let’s meet at 3pm tomorrow.'"
      - "Create a calendar invite for a meeting titled 'Team Sync' starting at '2023-10-05T09:00:00' and ending at '2023-10-05T10:00:00' at 'Conference Room A' with attendees alice@example.com, bob@example.com."
    """
    try:
        # The agent returns its response as a string.
        result = agent.run(user_command)
        return result
    except Exception as e:
        return f"An error occurred while executing the command: {e}"


# ------------------------------------
# For local testing (optional)
# ------------------------------------
if __name__ == "__main__":
    # Example test commands
    test_commands = [
        "Send an email to bob@example.com with subject 'Hello' and body 'How are you today?'",
        "Create a calendar invite for the meeting titled 'Team Sync' starting at '2023-10-05T09:00:00' and ending at '2023-10-05T10:00:00' at 'Conference Room A' with attendees alice@example.com, bob@example.com."
    ]
    for cmd in test_commands:
        print("User command:", cmd)
        result = execute_agent_command(cmd)
        print("Agent result:", result)
        print("-" * 50)
