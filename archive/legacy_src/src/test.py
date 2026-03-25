from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL")
)

response = client.chat.completions.create(
    model=os.getenv("LLM_MODEL_REASONING"),
    messages=[
        {"role": "user", "content": "hello"}
    ]
)
print(response.choices[0].message.content)