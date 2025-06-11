from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
)

response = client.chat.completions.create(
    model="deepseek/deepseek-chat-v3-0324:free",
    messages=[{"role": "user", "content": "1+1="}],
)

print(response.choices[0].message.content)

