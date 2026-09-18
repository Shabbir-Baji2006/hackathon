import os
from dotenv import load_dotenv
load_dotenv('.env')
key = os.environ.get("GROQ_API_KEY")

from groq import Groq
client = Groq(api_key=key)

SYSTEM = """You are LoopKit. You MUST respond with a valid JSON object matching this schema:
{
  "tool": "web_search"
}
"""
try:
    res = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": "hello"}],
        response_format={"type": "json_object"}
    )
    print(res.choices[0].message.content)
except Exception as e:
    print("ERROR:", e)
