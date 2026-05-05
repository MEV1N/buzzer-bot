import asyncio
import os
from dotenv import load_dotenv
from utils.ai import ask_buzzer

async def main():
    load_dotenv()
    print("API KEY:", os.getenv("GEMINI_API_KEY"))
    reply = await ask_buzzer("Say hello world!")
    print("REPLY:", reply)

if __name__ == '__main__':
    asyncio.run(main())
