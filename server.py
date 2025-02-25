import asyncio
import websockets
import json
import random

game_state = {
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

clients = {}
obstacle_images = ['Ambulance.png', 'Audi.png', 'Black_viper.png', 'Police.png', 'taxi.png', 'truck.png', 'Mini_truck.png']
game_started = False

async def handler(websocket):
    global game_started
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
                if len(clients) == 2 and not game_started:
                    game_started = True
                    print("Game started with 2 players!")
                    for client in clients:
                        await client.send(json.dumps({"type": "start"}))
            elif data["type"] == "move":
                game_state["players"][data["playerId"] - 1]["x"] = data["x"]
            elif data["type"] == "reset":
                game_state["players"][data["playerId"] - 1] = {
                    "x": (50 if data["playerId"] == 1 else 350) + 200 / 4,
                    "gameOver": False,
                    "score": 0
                }
                game_state["obstacles"] = []
                game_state["gameTime"] = 0
                game_state["speed"] = 3
                game_state["dashOffset"] = 0
                game_state["lastObstacleY"] = -250
    except websockets.ConnectionClosed:
        print(f"Player {player_id} disconnected")
        del clients[websocket]
        if len(clients) < 2:
            game_started = False
            print("Game paused: waiting for 2 players")
    finally:
        if websocket in clients:
            del clients[websocket]

async def game_loop():
    while True:
        if game_started and len(clients) == 2:
            game_state["gameTime"] += 1
            game_state["speed"] = 3 + game_state["gameTime"] // 120 * 0.1
            if game_state["speed"] > 15: game_state["speed"] = 15

            if game_state["gameTime"] > 60:
                highest_obstacle = min([o["y"] for o in game_state["obstacles"]]) if game_state["obstacles"] else 1000
                if highest_obstacle >= game_state["lastObstacleY"] + game_state["minGap"] and random.random() < 0.5:
                    side = "left" if random.random() < 0.5 else "right"
                    x = (50 if side == "left" else 50 + 200 / 2) + 200 / 4
                    img = random.choice(obstacle_images)
                    game_state["obstacles"].append({"x": x, "y": -100, "side": side, "img": img})
                    game_state["lastObstacleY"] = -20
                    print(f"Spawned obstacle: {side}, x: {x}, img: {img}")

            for o in game_state["obstacles"]:
                o["y"] += game_state["speed"]
                print(f"Obstacle updated: y={o['y']}")
            game_state["obstacles"] = [o for o in game_state["obstacles"] if o["y"] < 1000]

            for i, player in enumerate(game_state["players"]):
                if not player["gameOver"]:
                    for o in game_state["obstacles"]:
                        road_x = 50 if i == 0 else 350
                        obstacle_x = o["x"] if i == 0 else (o["x"] + 300)
                        if (o["y"] + 100 > 900 - 60 - 10 and
                            o["y"] < 900 and
                            abs(obstacle_x - player["x"]) < (40 / 2 + 80 / 2)):
                            player["gameOver"] = True
                            print(f"Player {i + 1} crashed at x={player['x']}, obstacle x={obstacle_x}")
                    if not player["gameOver"]:
                        player["score"] += game_state["speed"] / 60

            game_state["dashOffset"] -= game_state["speed"]
            if game_state["dashOffset"] <= -70: game_state["dashOffset"] += 70

        state_msg = json.dumps({"type": "state", **game_state})
        disconnected_clients = []
        for client in clients:
            try:
                await client.send(state_msg)
            except websockets.ConnectionClosed:
                disconnected_clients.append(client)
                print(f"Client {clients[client]} disconnected during broadcast")

        for client in disconnected_clients:
            if client in clients:
                del clients[client]

        await asyncio.sleep(1 / 60)

async def main():
    server = await websockets.serve(handler, "localhost", 8765)
    asyncio.create_task(game_loop())
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())