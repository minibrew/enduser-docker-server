import asyncio
from backend.minibrew_client import MiniBrewClient
import os
from dotenv import load_dotenv

async def main():
    load_dotenv()
    token = os.environ.get("MINIBREW_API_KEY")
    client = MiniBrewClient("https://api.minibrew.io/v1/", token)
    recipes = await client.get_recipes()
    if recipes:
        print("First recipe:", recipes[0])
    else:
        print("No recipes")

if __name__ == "__main__":
    asyncio.run(main())
