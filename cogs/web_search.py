# cogs/web_search.py
import os
import json
import requests
import validators
import pytz
from datetime import datetime, timedelta
from datetime import time as dt_time
from azure.identity import DefaultAzureCredential
from azure.keyvault.secrets import SecretClient

# Remove direct import of openai
# from utils.fetch_page_content import fetch_page_content  # Ensure this is synchronous

from utils.fetch_page_content import fetch_page_content  # Ensure this is synchronous

est = pytz.timezone('America/New_York')
current_date = datetime.now(est).strftime("%Y-%m-%d")
current_time = datetime.now(est)

class WebSearchCog:
    def __init__(self, openai_client):
        """
        Initialize WebSearchCog with an existing OpenAI client.

        :param openai_client: An instance of the OpenAI client to use for generating search terms.
        """
        # **Initialize Azure Key Vault Client**
        key_vault_name = os.getenv("KEYVAULT_NAME")  # **Modified Line**
        key_vault_uri = f"https://{key_vault_name}.vault.azure.net"

        try:
            credential = DefaultAzureCredential()
            secret_client = SecretClient(vault_url=key_vault_uri, credential=credential)

            # **Fetch secrets from Key Vault**
            self.search_api_key = secret_client.get_secret("GOOGLE-API-KEY").value  # **Added Line**
            self.search_engine_id = secret_client.get_secret("SEARCH-ENGINE-ID").value  # **Added Line**

        except Exception as e:
            print(f"Failed to fetch secrets from Key Vault: {e}")
            raise  # **Added Line**

        self.openai_client = openai_client

        # self.search_api_key = os.getenv('GOOGLE_API_KEY')
        # self.search_engine_id = os.getenv('SEARCH_ENGINE_ID')
        self.search_url = "https://www.googleapis.com/customsearch/v1"


    def generate_search_terms(self, user_input, history):
        """
        Use the provided OpenAI client to generate optimized search terms from user input.
        """
        prompt = (
            f"Generate concise search terms for a Google search based on the user input. Return only the search terms, with no additional formatting or headings. Be as brief and relevant as possible. The current date, if relevant, is {current_date}. Prefer .mil domains when applicable. Do not use quotation marks."
        )

        messages = [
                    {"role": "system", "content": prompt},
                    *history,
                    {"role": "user", "content": f"User Input: {user_input}\n"}
                ]

        try:
            print()
            print('messages', messages)
            print('user_input', user_input)
            print()
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",  # Specify the desired model
                messages=messages,
                max_tokens=60,
                n=1,
                stop=None,
                temperature=0.4,
            )
            # Extract the generated search terms
            search_terms = response.choices[0].message.content
            # Optionally, parse the search terms if they're in a list format
            # For simplicity, assume the LLM returns a comma-separated string
            optimized_query = search_terms.split('\n')[0]  # Take the first line
            return optimized_query
        except Exception as e:
            print(f"Error generating search terms with LLM: {e}")
            # Fallback to original query if LLM fails
            return user_input

    def web_search(self, query, history):
        """Perform a web search using the Google Custom Search API."""
        # First, generate optimized search terms using the LLM
        optimized_query = self.generate_search_terms(query, history)
        print(f"Query: {query}\n")
        print(f"Optimized Query: {optimized_query}")

        if validators.url(optimized_query):
            content = fetch_page_content(optimized_query)
            if content:
                return content[:3000]  # Limit content length
            else:
                return "Couldn't fetch information from the provided URL."
        else:
            params = {
                "key": self.search_api_key,
                "cx": self.search_engine_id,
                "q": optimized_query,
            }

            try:
                response = requests.get(self.search_url, params=params, timeout=10)
                if response.status_code == 200:
                    search_results = response.json()
                    items = search_results.get('items', [])
                    if not items:
                        query += f'This is what you provided last time and resulted in no search results. Try again, but be more general to allow a broader search:\n{optimized_query}'
                        optimized_query = self.generate_search_terms(query, history)
                        print(f"Second Optimized Query: {optimized_query}")
                        params = {
                            "key": self.search_api_key,
                            "cx": self.search_engine_id,
                            "q": optimized_query,
                        }
                        try:
                            response = requests.get(self.search_url, params=params, timeout=10)
                            if response.status_code != 200:
                                error_content = response.text
                                print(f"Error fetching search results: {response.status_code}")
                                print(f"Error details: {error_content}")
                                return "An error occurred while performing the web search."
                        except Exception as e:
                            print(f"Exception during web search: {e}")
                            return "An error occurred while performing the web search."
                    # print()
                    # print('search_results', search_results)
                    return self.fetch_search_content(search_results)
                else:
                    error_content = response.text
                    print(f"Error fetching search results: {response.status_code}")
                    print(f"Error details: {error_content}")
                    return "An error occurred while performing the web search."
            except Exception as e:
                print(f"Exception during web search: {e}")
                return "An error occurred while performing the web search."

    def fetch_search_content(self, search_results):
        """Fetch content from search results."""
        if not search_results:
            return "Couldn't fetch information from the internet."
        
        items = search_results.get('items', [])
        if not items:
            return "No search results found."

        urls = [item.get('link') for item in items[:5] if item.get('link')]
        if not urls:
            return "No valid URLs found in search results."

        contents = []
        for url in urls:
            print(f"Fetching content from {url}")
            content = fetch_page_content(url)
            # print('og content', content)
            if content:
                content = f"From {url}:" + content
            # print('new content', content)
            if content:
                contents.append(content[:3000])  # Limit content length

        return '\n'.join(contents) if contents else "No detailed information found."
