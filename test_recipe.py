import traceback
import sys
import asyncio
import os

from dotenv import load_dotenv
from backend.minibrew_client import MiniBrewClient

async def main():
    load_dotenv()
    client = MiniBrewClient('https://api.minibrew.io/v1/', os.environ.get('MINIBREW_API_KEY'))
    try:
        detail = await client.get_recipe('1307287')
        print(f"Detail type: {type(detail)}")
        if isinstance(detail, list):
            print(f"List length: {len(detail)}")
            if len(detail) > 0:
                print(f"First element type: {type(detail[0])}")
        
        from backend.recipe_service import RecipeService
        svc = RecipeService(client)
        detail2 = await svc.get_recipe('1307287')
        steps = []
        try:
            steps = await svc.get_recipe_steps('1307287')
        except Exception:
            pass
        
        if not steps and detail2:
            recipe_obj = detail2[0] if isinstance(detail2, list) and len(detail2) > 0 else detail2
            mashing = recipe_obj.get("mashing", {}) if isinstance(recipe_obj, dict) else {}
            print("Mashing:", mashing)
            boiling = recipe_obj.get("boiling", {}) if isinstance(recipe_obj, dict) else {}
            print("Boiling:", boiling)
            
    except Exception as e:
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
