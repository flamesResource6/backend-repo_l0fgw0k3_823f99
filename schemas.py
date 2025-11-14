"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal

# Core user of the game
class Player(BaseModel):
    username: str = Field(..., description="Unique username")
    trophies: int = Field(0, ge=0)
    gold: int = Field(1000, ge=0)
    gems: int = Field(50, ge=0)
    deck: List[str] = Field(default_factory=list, description="List of card ids in deck")

# Card definitions (static data seeded once)
class Card(BaseModel):
    card_id: str = Field(..., description="Unique card id")
    name: str
    cost: int = Field(..., ge=1, le=10)
    role: Literal["melee", "ranged", "tank", "assassin"] = "melee"
    hp: int = Field(..., ge=1)
    dmg: int = Field(..., ge=0)
    speed: float = Field(1.0, ge=0.2, le=5.0, description="Tiles per tick")
    range: float = Field(1.0, ge=0.5, le=5.0)

# Unit instance on the board
class Unit(BaseModel):
    owner: Literal["player", "ai"]
    card_id: str
    x: float = 0.0
    lane: int = 1  # 0 left, 1 center, 2 right
    hp: int

class Tower(BaseModel):
    side: Literal["player", "ai"]
    lane: Literal["left", "right", "king"]
    hp: int = 1000

class Match(BaseModel):
    player_id: str
    status: Literal["active", "finished"] = "active"
    time: int = 180  # seconds remaining
    elixir: int = 5
    units: List[Unit] = Field(default_factory=list)
    towers: List[Tower] = Field(default_factory=list)
    last_tick_ms: int = 0

# Example schemas kept for reference (not used directly by app UI)
class User(BaseModel):
    name: str
    email: str
    address: str
    age: Optional[int] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    description: Optional[str] = None
    price: float
    category: str
    in_stock: bool = True
