import asyncio
import websockets
import json
import random
import os

PORT = int(os.getenv("PORT", 8765))

player_usernames = [None, None]
obstacle_images = ['obstacleCarBlue.png', 'obstacleCarGreen.png', 'obstacleCarWhite.png']

def reset_game_state():
    return {
        "players": [
            {"x": 100, "gameOver": False, "score": 0, "username": player_usernames[0] or "Player 1"},
            {"x": 400, "gameOver": False, "score": 0, "username": player_usernames[1] or "Player 2"}
        ],
        "obstacles": [],
        "gameTime": 0,
        "speed": 5,  # Increased base speed from 3 to 5
        "dashOffset": 0,
        "lastObstacleY": -250,
        "minGap": 250
    }

game_state = reset_game_state()
clients = {}
game_started = False

async def handler(websocket):
    global game_started, game_state, clients, player_usernames
    player_id = len(clients) + 1
    if player_id > 2:
        await websocket.send(json.dumps({"type": "error", "message": "Game is full"}))
        return
    clients[websocket] = player_id
    await websocket.send(json.dumps({"type": "init", "playerId": player_id}))

    try:
        async for message in websocket:
            data = json.loads(message)
            if data["type"] == "join":
                print(f"Player {player_id} joined: {data['username']}")
                player_usernames[player_id - 1] = data["username"]
                if len(clients) == 2:
                    game_state = reset_game_state()
                    game_started = True
                    print("Game started with 2 players!")
                    for client in clients:
                        await client.send(json.dumps({"type": "start"}))
            elif data["type"] == "move":
                if not game_state["players"][player_id - 1]["gameOver"]:
                    game_state["players"][player_id - 1]["x"] = data["x"]
                    await broadcast_state()
    except websockets.ConnectionClosed:
        print(f"Player {player_id} disconnected")
        if websocket in clients:
            del clients[websocket]
        if len(clients) < 2 and game_started:
            game_started = False
            game_state = reset_game_state()
            player_usernames = [None, None]
            print("Game reset: waiting for 2 players")

async def broadcast_state():
    """Helper function to broadcast game state to all clients."""
    global clients, game_state
    state_msg = json.dumps({"type": "state", **game_state})
    for client in list(clients.keys()):
        try:
            await client.send(state_msg)
        except websockets.ConnectionClosed:
            if client in clients:
                print(f"Client {clients[client]} disconnected during broadcast")
                del clients[client]

async def game_loop():
    global game_started, game_state, clients, player_usernames
    while True:
        if game_started and len(clients) == 2:
            state_changed = False
            any_game_over = any(p["gameOver"] for p in game_state["players"])
            
            if not any_game_over:
                game_state["gameTime"] += 1
                # Speed increases by 0.2 every 60 ticks, max 20
                game_state["speed"] = min(5 + (game_state["gameTime"] // 60) * 0.2, 20)
                print(f"Current speed: {game_state['speed']}")  # Debug log

                if random.random() < 0.05:
                    last_y = min([o["y"] for o in game_state["obstacles"]] or [float('inf')])
                    if last_y > game_state["minGap"]:
                        lane = random.choice([100, 200, 400, 500])
                        img = random.choice(obstacle_images)
                        game_state["obstacles"].append({"x": lane, "y": -60, "img": img})
                        state_changed = True

                for o in game_state["obstacles"]:
                    o["y"] += game_state["speed"]
                    state_changed = True
                game_state["obstacles"] = [o for o in game_state["obstacles"] if o["y"] < 800]

                for i, player in enumerate(game_state["players"]):
                    if not player["gameOver"]:
                        for o in game_state["obstacles"]:
                            if (o["y"] + 60 >= 650 and o["y"] + 60 <= 710 and
                                abs(o["x"] - player["x"]) < 40):
                                player["gameOver"] = True
                                print(f"Player {i + 1} crashed at obstacle y={o['y']}")
                                state_changed = True
                        if not player["gameOver"]:
                            player["score"] += game_state["speed"] / 60
                            state_changed = True

                game_state["dashOffset"] -= game_state["speed"]
                if game_state["dashOffset"] <= -70:
                    game_state["dashOffset"] += 70
                    state_changed = True
            else:
                game_started = False
                print("Game over: one player crashed")
                state_changed = True
                await broadcast_state()
                game_state = reset_game_state()
                clients.clear()
                player_usernames = [None, None]
                print("Server fully reset: ready for new game")

            if state_changed and not any_game_over:
                await broadcast_state()

        await asyncio.sleep(0.05)  # ~20 FPS

async def main():
    server = await websockets.serve(handler, "0.0.0.0", PORT)
    asyncio.create_task(game_loop())
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())