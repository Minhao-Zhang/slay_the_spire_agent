import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(
    api_key=os.getenv("API_KEY", ""),
    base_url=os.getenv("API_BASE_URL", "https://api.openai.com/v1"),
)

response = client.chat.completions.create(
    model=os.getenv("DECISION_MODEL", "gpt-4o"),
    messages=[
        {"role": "user", "content": "hello"}
    ]
)
print(response.choices[0].message.content)