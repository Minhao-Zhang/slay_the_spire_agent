from typing import List, Dict, Optional
from openai import OpenAI
from src.llm.config import config

# Initialize the OpenAI client using our configuration
client = OpenAI(
    api_key=config.api_key,
    base_url=config.base_url,
)

def generate_one_off(prompt: str, system_prompt: Optional[str] = None, use_reasoning_model: bool = False) -> str:
    """
    Sends a single prompt to the LLM and returns the text response.

    Args:
        prompt: The user query or command.
        system_prompt: Optional instructions for the model's persona/behavior.
        use_reasoning_model: If True, uses the reasoning model, otherwise uses the fast model.
    """
    model_name = config.model_reasoning if use_reasoning_model else config.model_fast

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error calling LLM: {e}")
        return ""


class ChatSession:
    """A class to manage a multi-turn conversation sequence."""
    
    def __init__(self):
        self.history: List[Dict[str, str]] = []

    def add_system_message(self, content: str):
        self.history.append({"role": "system", "content": content})

    def add_user_message(self, content: str):
        self.history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str):
        self.history.append({"role": "assistant", "content": content})

    def generate_response(self, use_reasoning_model: bool = True) -> str:
        """
        Sends the entire conversation history to the LLM, appends the received
        response to history, and returns the response text.
        """
        model_name = config.model_reasoning if use_reasoning_model else config.model_fast

        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=self.history
            )
            response_text = response.choices[0].message.content
            # Automatically append the assistant's reply to state
            self.add_assistant_message(response_text)
            return response_text
        except Exception as e:
            print(f"Error calling LLM in ChatSession: {e}")
            return ""
