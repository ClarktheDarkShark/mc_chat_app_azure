# cogs/orchestration_analysis.py
from flask import request
from models import UploadedFile
import json
import re
import traceback

class OrchestrationAnalysisCog:
    def __init__(self, openai_client):
        self.client = openai_client

    def analyze_user_orchestration(self, user_message, conversation_history, session_id):
        """
        Analyze user orchestration using OpenAI and return a JSON object.
        """
        try:
            # Fetch the list of uploaded files for the current session
            uploaded_files = UploadedFile.query.filter_by(session_id=session_id).all()
            file_list = "\n".join([f"File ID: {file.id}, Filename: {file.original_filename}" for file in uploaded_files])

            print(flush=True)
            print(f'file_list: {file_list}', flush=True)
            print(flush=True)

            analysis_prompt = [
                {
                    'role': 'system', 
                    'content': (
                        'As an AI assistant, analyze the user input, including the last 5 user queries, and output a JSON object with the following keys:\n'
                        '- "image_generation": (boolean)\n'
                        '- "image_prompt": (string)\n'
                        '- "internet_search": (boolean)\n'
                        '- "file_orchestration": (boolean)\n'
                        '- "file_ids": (list of strings)\n'  # Updated key
                        '- "active_users": (boolean)\n'
                        '- "code_orchestration": (boolean)\n'
                        '- "code_structure_orchestration": (boolean)\n'
                        '- "rand_num": (list)\n\n'
                        'Respond with only the JSON object and no additional text.\n\n'
                        'Guidelines:\n'
                        '1. **image_generation** should be True only when an image is requested. Example: "Create an image of a USMC officer saluting", "make an image of an amphibious assault." \n'
                        '2. **image_prompt** should contain the prompt for image generation if **image_generation** is True.\n'
                        '3. **internet_search** should be True when the user asks for information that might require an internet search. If asking about an uploaded file, set to False. If they say "That is wrong," set to True.\n'
                        '4. **file_orchestration** should be True when the user asks for information about any uploaded file. This includes:\n'
                        f'   - Specific file references by their plain text titles from this list: {file_list}.\n'
                        f'   - General inquiries about the uploaded files, such as "What files are uploaded?" or "Show me the uploaded files."\n'
                        '5. **file_ids** should contain a list of file IDs for the requested files if **file_orchestration** is True. Detect file references in the format "FILE:<id>". If the request is general, return a list of all file IDs.\n'  # Updated guideline
                        '6. **active_users** should be True if there is a question about the most active users.\n'
                        '7. **code_orchestration** should be True when the user is asking about code-related queries. Anytime "your code" is in the User Input, this should be True.\n'
                        '8. **code_structure_orchestration** should be True only when the user asks specifically to "visualize" the code base architecture or structure. Return False if visualize (or a related word) is not in the request.\n'
                        '9. **rand_num** should contain [lowest_num, highest_num] if the user requests a random number within a range.\n\n'
                        'Respond in JSON format.\nIMPORTANT: Boolean values only: True or False.'
                    )
                },
                {'role': 'user', 'content': f"User input: '{user_message}'\n\nDetermine the user's orchestration and required actions."}
            ]


            print('Orchestrating input...', flush=True)
            # Include the last 5 messages for context, excluding system messages
            user_assistant_messages = [msg for msg in conversation_history if msg['role'] in ['user', 'assistant']]
            last_five = user_assistant_messages[-5:]
            analysis_prompt.extend(last_five)

            analysis_prompt.append({"role": "user", "content": user_message})

            # print(f'analysis_prompt: {analysis_prompt}', flush=True)

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=analysis_prompt,
                max_tokens=300,
                temperature=0
            )

            orchestration_json = response.choices[0].message.content.strip()

            print(f'orchestration_json: {orchestration_json}', flush=True)
            # Handle markdown-wrapped JSON
            if orchestration_json.startswith("```json"):
                orchestration_json = orchestration_json[7:-3].strip()
            elif orchestration_json.startswith("```") and orchestration_json.endswith("```"):
                orchestration_json = orchestration_json[3:-3].strip()

            # Ensure the response is valid JSON
            orchestration = json.loads(orchestration_json)

            # Extract file_ids if file_orchestration is detected
            if orchestration.get("file_orchestration", False):
                # Find all occurrences of FILE:<id>
                matches = re.findall(r"FILE:(\d+)", user_message)
                if matches:
                    orchestration["file_ids"] = matches
                else:
                    # If no specific files are mentioned, return all file IDs
                    orchestration["file_ids"] = [str(file.id) for file in uploaded_files]


            return orchestration
        except Exception as e:
            print(f'Error in analyzing user orchestration: {e}')
            traceback.print_exc()
            # Return default orchestration if analysis fails
            return {
                "image_generation": False,
                "image_prompt": "",
                "internet_search": False,
                "file_orchestration": False,
                "file_id": [],
                "active_users": False,
                "code_orchestration": False,
                "code_structure_orchestration": False,  # New key
                "rand_num": []
            }
