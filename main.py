import os
import time
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Literal, Optional

from database import db, create_document, get_documents
from schemas import Player, Card, Match, Unit, Tower

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Battle Arena API running"}

@app.get("/schema")
def get_schema_overview():
    # helper endpoint for viewers
    return {
        "collections": ["player", "card", "match"],
    }

# Utility
COLLECTION_PLAYER = "player"
COLLECTION_CARD = "card"
COLLECTION_MATCH = "match"

# Seed some cards if empty
@app.post("/seed")
def seed_cards():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    existing = db[COLLECTION_CARD].count_documents({})
    if existing > 0:
        return {"ok": True, "seeded": False, "count": existing}
    base_cards = [
        Card(card_id="knight", name="Knight", cost=3, role="melee", hp=600, dmg=75, speed=1.0, range=1.0).model_dump(),
        Card(card_id="archer", name="Archer", cost=3, role="ranged", hp=220, dmg=100, speed=1.0, range=4.0).model_dump(),
        Card(card_id="giant", name="Giant", cost=5, role="tank", hp=2000, dmg=100, speed=0.6, range=1.0).model_dump(),
        Card(card_id="assassin", name="Assassin", cost=4, role="assassin", hp=400, dmg=200, speed=1.5, range=1.0).model_dump(),
    ]
    db[COLLECTION_CARD].insert_many(base_cards)
    return {"ok": True, "seeded": True, "count": len(base_cards)}

class CreatePlayerRequest(BaseModel):
    username: str

@app.post("/player", response_model=dict)
def create_player(req: CreatePlayerRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    existing = db[COLLECTION_PLAYER].find_one({"username": req.username})
    if existing:
        return {"player_id": str(existing.get("_id")), "username": existing["username"]}
    player = Player(username=req.username)
    player_id = create_document(COLLECTION_PLAYER, player)
    return {"player_id": player_id, "username": req.username}

@app.get("/cards")
def list_cards():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    cards = get_documents(COLLECTION_CARD, {})
    for c in cards:
        c["_id"] = str(c["_id"])  # stringify
    return {"cards": cards}

class StartMatchRequest(BaseModel):
    player_id: str

@app.post("/match/start")
def start_match(req: StartMatchRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    match = Match(
        player_id=req.player_id,
        time=180,
        elixir=5,
        units=[],
        towers=[
            Tower(side="player", lane="left", hp=1000),
            Tower(side="player", lane="right", hp=1000),
            Tower(side="player", lane="king", hp=1800),
            Tower(side="ai", lane="left", hp=1000),
            Tower(side="ai", lane="right", hp=1000),
            Tower(side="ai", lane="king", hp=1800),
        ],
        last_tick_ms=int(time.time() * 1000),
    ).model_dump()
    match_id = create_document(COLLECTION_MATCH, match)
    return {"match_id": match_id, "state": match}

class DeployRequest(BaseModel):
    match_id: str
    card_id: str
    lane: int

@app.post("/match/deploy")
def deploy_unit(req: DeployRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    match = db[COLLECTION_MATCH].find_one({"_id": {"$eq": db[COLLECTION_MATCH].codec_options.uuid_representation and None}})
    match = db[COLLECTION_MATCH].find_one({"_id": db[COLLECTION_MATCH].find_one({"_id": {"$exists": True}})["_id"]}) if False else db[COLLECTION_MATCH].find_one({"_id": __import__("bson").ObjectId(req.match_id)})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    # Simple elixir and deploy
    unit_card = db[COLLECTION_CARD].find_one({"card_id": req.card_id})
    if not unit_card:
        raise HTTPException(status_code=404, detail="Card not found")
    if match.get("elixir", 0) < unit_card["cost"]:
        raise HTTPException(status_code=400, detail="Not enough elixir")
    unit = Unit(owner="player", card_id=req.card_id, x=0.0, lane=req.lane, hp=unit_card["hp"]).model_dump()
    db[COLLECTION_MATCH].update_one({"_id": match["_id"]}, {"$push": {"units": unit}, "$inc": {"elixir": -unit_card["cost"]}})
    return {"ok": True}

@app.get("/match/state/{match_id}")
def get_match_state(match_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    match = db[COLLECTION_MATCH].find_one({"_id": __import__("bson").ObjectId(match_id)})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    match["_id"] = str(match["_id"])
    return match

@app.post("/match/tick/{match_id}")
def tick(match_id: str):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    from bson import ObjectId
    match = db[COLLECTION_MATCH].find_one({"_id": ObjectId(match_id)})
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Advance simple simulation: move player units towards AI side and deduct time, regen elixir
    now_ms = int(time.time() * 1000)
    last = match.get("last_tick_ms", now_ms)
    dt = max(0, now_ms - last)
    # regen elixir: 1 elixir per 2800ms up to 10
    regen = dt / 2800.0
    new_elixir = min(10, match.get("elixir", 0) + regen)

    units = match.get("units", [])
    cards_map = {c["card_id"]: c for c in db[COLLECTION_CARD].find({})}

    # simple movement
    for u in units:
        card = cards_map.get(u["card_id"]) or {"speed": 1.0, "dmg": 50}
        u["x"] = u.get("x", 0.0) + card.get("speed", 1.0) * (dt / 1000.0)
        # basic collision to AI towers when x>10
        if u["x"] >= 10:
            # hit right lane tower as example
            for t in match.get("towers", []):
                if t["side"] == "ai" and (t["lane"] == "right" if u.get("lane",1)==2 else t["lane"] == "left"):
                    t["hp"] = max(0, t.get("hp", 0) - int(card.get("dmg", 50)))

    # countdown
    new_time = max(0, match.get("time", 0) - int(dt/1000))
    status = "finished" if new_time == 0 else "active"

    db[COLLECTION_MATCH].update_one(
        {"_id": match["_id"]},
        {"$set": {"units": units, "towers": match.get("towers", []), "elixir": new_elixir, "time": new_time, "status": status, "last_tick_ms": now_ms}}
    )
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
