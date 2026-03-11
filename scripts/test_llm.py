import sys
import os

# Ensure the src directory is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.llm.client import generate_one_off, ChatSession
from src.llm.config import config

def test_one_off():
    print(f"--- Testing One-Off Generation ({config.model_fast}) ---")
    prompt = "Give me one valid move name for an Ironclad card."
    response = generate_one_off(prompt, system_prompt="You are an expert Slay the Spire player.", use_reasoning_model=False)
    print(f"User: {prompt}\nLLM: {response}\n")

def test_chat_session():
    print(f"--- Testing Multi-Turn Session ({config.model_reasoning}) ---")
    session = ChatSession()
    session.add_system_message("You are an expert in Slay the Spire. Respond very concisely.")
    
    first_msg = "Hello! I'm struggling with the game."
    print(f"User: {first_msg}")
    session.add_user_message(first_msg)
    response = session.generate_response(use_reasoning_model=True)
    print(f"LLM: {response}\n")

    second_msg = "What is a good starting tip for playing the Ironclad?"
    print(f"User: {second_msg}")
    session.add_user_message(second_msg)
    response = session.generate_response(use_reasoning_model=True)
    print(f"LLM: {response}\n")

def main():
    if not config.api_key:
        print("Warning: LLM_API_KEY environment variable is missing!")
        print("Please configure .env before running tests.")
        return

    test_one_off()
    test_chat_session()

if __name__ == "__main__":
    main()
