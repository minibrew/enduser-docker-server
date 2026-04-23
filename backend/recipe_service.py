"""
Recipe management.

Provides read access to the MiniBrew recipe library and recipe steps.
Recipes define the beer being brewed — name, style, mash schedule,
boil steps, fermentation profile, and hop/ingredient additions.
"""

from typing import Any

from minibrew_client import MiniBrewClient
from state_store import get_state_store


class RecipeService:
    def __init__(self, client: MiniBrewClient) -> None:
        self._client = client

    async def list_recipes(self) -> list[dict[str, Any]]:
        """
        Fetch all recipes from GET /recipes/.
        The response is a list of recipe summary objects.
        """
        return await self._client.get_recipes()

    async def get_recipe(self, recipe_id: str) -> dict[str, Any]:
        """Fetch a single recipe detail from GET /recipes/{id}/."""
        return await self._client.get_recipe(recipe_id)

    async def get_recipe_steps(self, recipe_id: str) -> list[dict[str, Any]]:
        """
        Fetch the step-by-step brew schedule for a recipe.
        Each step has type (mash, boil, ferment), target temperature,
        hold time, and any ingredient additions.
        """
        return await self._client.get_recipe_steps(recipe_id)

    async def create_recipe(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new recipe via POST /recipes/."""
        return await self._client.create_recipe(data)

    def list_cached_recipes(self) -> list[dict[str, Any]]:
        """Return cached recipes from the local state store."""
        return get_state_store().list_recipes()
