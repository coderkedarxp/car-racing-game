import asyncio
import websockets
import json
import random
import os

PORT = int(os.getenv("PORT", 8765))

def reset_game_state():
    return {
        "players": [
            {"x": 50 + 200 / 4, "gameOver": False, "score": 0},
            {"x": 350 + 200 / 4, "gameOver": False, "score": 0}
        ],
        "obstacles": [],
        "gameTime": 0,
        "speed": 3,
        "dashOffset": 0,
        "lastObstacleY": -250,
        "minGap": 250
    }

game_state = reset_game_state()
clients = {}
obstacle_images = ['obstacleCarBlue.png', 'obstacleCarGreen.png', 'obstacleCarWhite.png']
game_started = False

async def handler(websocket):
    global game_started, game_state
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
                if len(clients) == 2:
                    game_state = reset_game_state()
                    game_started = True
                    print("Game started with 2 new players!")
                    for client in clients:
                        await client.send(json.dumps({"type": "start"}))
            elif data["type"] == "move":
                if not game_state["players"][data["playerId"] - 1]["gameOver"]:
                    game_state["players"][data["playerId"] - 1]["x"] = data["x"]
    except websockets.ConnectionClosed:
        print(f"Player {player_id} disconnected")
        if websocket in clients:
            del clients[websocket]
        if len(clients) < 2:
            game_started = False
            print("Game paused: waiting for 2 players")
    finally:
        if websocket in clients:
            del clients[websocket]

async def game_loop():
    global game_started, game_state
    while True:
        if game_started and len(clients) == 2:
            both_games_over = all(p["gameOver"] for p in game_state["players"])
            
            if not both_games_over:
                game_state["gameTime"] += 1
                game_state["speed"] = 3 + game_state["gameTime"] // 120 * 0.1
                if game_state["speed"] > 15: game_state["speed"] = 15

                # Spawn obstacles with proper gaps
                if game_state["gameTime"] > 60 and random.random() < 0.5:
                    lowest_obstacle = max([o["y"] for o in game_state["obstacles"]]) if game_state["obstacles"] else -float('inf')
                    if lowest_obstacle <= game_state["lastObstacleY"] - game_state["minGap"]:
                        side = "left" if random.random() < 0.5 else "right"
                        x = (50 if side == "left" else 50 + 200 / 2) + 200 / 4
                        img = random.choice(obstacle_images)
                        game_state["obstacles"].append({"x": x, "y": -60, "side": side, "img": img})
                        game_state["lastObstacleY"] = -60  # Track Y position of the last obstacle

                # Move obstacles
                for o in game_state["obstacles"]:
                    o["y"] += game_state["speed"]
                game_state["obstacles"] = [o for o in game_state["obstacles"] if o["y"] < 800]

                # Check collisions
                for i, player in enumerate(game_state["players"]):
                    if not player["gameOver"]:
                        player_road_x = 50 if i == 0 else 350
                        for o in game_state["obstacles"]:
                            if i == 0:
                                obstacle_x = o["x"]  # Player 1 uses obstacle x as-is
                            else:  # Player 2
                                obstacle_x = o["x"] + 300 if o["side"] == "left" else o["x"] + 200  # Adjust for Player 2's road
                            if (o["y"] + 60 > 730 and  # Obstacle bottom > car top
                                o["y"] <= 790 and      # Obstacle top <= car bottom
                                abs(obstacle_x - player["x"]) < 40):  # Horizontal collision
                                player["gameOver"] = True
                                print(f"Player {i + 1} crashed at x={player['x']}, obstacle x={obstacle_x}, y={o['y']}")
                        if not player["gameOver"]:
                            player["score"] += game_state["speed"] / 60

                # Update dash offset
                game_state["dashOffset"] -= game_state["speed"]
                if game_state["dashOffset"] <= -70: game_state["dashOffset"] += 70
            else:
                game_state = reset_game_state()
                game_started = False
                print("Both players game over - game reset")

        # Broadcast game state
        state_msg = json.dumps({"type": "state", **game_state})
        disconnected_clients = []
        for client in list(clients.keys()):
            try:
                await client.send(state_msg)
            except websockets.ConnectionClosed:
                disconnected_clients.append(client)

        # Clean up disconnected clients
        for client in disconnected_clients:
            if client in clients:
                print(f"Client {clients[client]} disconnected during broadcast")
                del clients[client]

        await asyncio.sleep(1 / 30)

async def main():
    server = await websockets.serve(handler, "0.0.0.0", PORT)
    asyncio.create_task(game_loop())
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())