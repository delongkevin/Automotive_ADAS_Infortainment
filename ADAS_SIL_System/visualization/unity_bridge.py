"""
Unity/Unreal Engine Bridge

WebSocket-based communication bridge for 3D visualization integration.

Copyright Magna Electronics. All rights reserved.
"""

import asyncio
import websockets
import json
import logging
from typing import Dict, Optional, Set
import threading

logger = logging.getLogger(__name__)


class UnityBridge:
    """
    WebSocket server for Unity/Unreal Engine integration.

    Streams simulation state to 3D visualization engine in real-time.
    """

    def __init__(self, host: str = 'localhost', port: int = 5555):
        """
        Initialize Unity bridge.

        Args:
            host: Server host address
            port: Server port
        """
        self.host = host
        self.port = port
        self.server = None
        self.clients: Set[websockets.WebSocketServerProtocol] = set()
        self.is_running = False
        self.server_thread = None

        logger.info(f"Unity bridge initialized on {host}:{port}")

    def start(self):
        """Start the WebSocket server in a background thread."""
        if self.is_running:
            logger.warning("Bridge already running")
            return

        self.is_running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()

        logger.info("Unity bridge server started")

    def _run_server(self):
        """Run the WebSocket server (internal)."""
        asyncio.run(self._async_server())

    async def _async_server(self):
        """Async WebSocket server implementation."""
        async with websockets.serve(self._handle_client, self.host, self.port):
            logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")
            await asyncio.Future()  # Run forever

    async def _handle_client(self, websocket, path):
        """
        Handle new client connection.

        Args:
            websocket: WebSocket connection
            path: Connection path
        """
        self.clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info(f"Unity client connected: {client_addr}")

        try:
            async for message in websocket:
                # Handle incoming messages from Unity (e.g., commands)
                await self._handle_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Unity client disconnected: {client_addr}")
        finally:
            self.clients.remove(websocket)

    async def _handle_message(self, websocket, message: str):
        """
        Handle incoming message from Unity.

        Args:
            websocket: WebSocket connection
            message: JSON message string
        """
        try:
            data = json.loads(message)
            command = data.get('command')

            if command == 'ping':
                await websocket.send(json.dumps({'response': 'pong'}))
            elif command == 'get_status':
                await websocket.send(json.dumps({'status': 'running' if self.is_running else 'stopped'}))

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def send_state(self, state: Dict):
        """
        Send simulation state to all connected Unity clients.

        Args:
            state: Current simulation state dictionary
        """
        if not self.clients:
            return

        # Format state for Unity
        unity_message = self._format_for_unity(state)

        # Send to all clients (synchronous wrapper for async)
        asyncio.run(self._broadcast(unity_message))

    async def _broadcast(self, message: Dict):
        """
        Broadcast message to all clients.

        Args:
            message: Message dictionary
        """
        if not self.clients:
            return

        message_json = json.dumps(message)
        await asyncio.gather(
            *[client.send(message_json) for client in self.clients],
            return_exceptions=True
        )

    def _format_for_unity(self, state: Dict) -> Dict:
        """
        Format simulation state for Unity consumption.

        Args:
            state: Simulation state

        Returns:
            Unity-formatted message dictionary
        """
        vehicle = state.get('vehicle', {})
        adas = state.get('adas', {})

        # Build Unity message
        unity_msg = {
            'type': 'state_update',
            'timestamp': state.get('time', 0.0),
            'vehicle': {
                'position': {
                    'x': vehicle.get('position', {}).get('x', 0.0),
                    'y': vehicle.get('position', {}).get('y', 0.0),
                    'z': vehicle.get('position', {}).get('z', 0.0)
                },
                'rotation': {
                    'roll': vehicle.get('orientation', {}).get('roll', 0.0),
                    'pitch': vehicle.get('orientation', {}).get('pitch', 0.0),
                    'yaw': vehicle.get('orientation', {}).get('yaw', 0.0)
                },
                'velocity': {
                    'vx': vehicle.get('velocity', {}).get('vx', 0.0),
                    'vy': vehicle.get('velocity', {}).get('vy', 0.0),
                    'vz': vehicle.get('velocity', {}).get('vz', 0.0),
                    'speed': vehicle.get('velocity', {}).get('speed', 0.0)
                },
                'controls': vehicle.get('controls', {})
            },
            'adas': {}
        }

        # Add ADAS status
        for feature_name, feature_status in adas.items():
            unity_msg['adas'][feature_name] = feature_status

        return unity_msg

    def stop(self):
        """Stop the WebSocket server."""
        self.is_running = False
        logger.info("Unity bridge stopped")
