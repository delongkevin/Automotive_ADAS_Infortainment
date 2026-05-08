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
        self.server_loop = None
        self.shutdown_event = None
        self.clients_lock = threading.Lock()
        self.server_started = threading.Event()

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
        self.server_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.server_loop)
        self.shutdown_event = asyncio.Event()

        try:
            self.server_loop.run_until_complete(self._async_server())
        finally:
            pending_tasks = asyncio.all_tasks(self.server_loop)
            for task in pending_tasks:
                task.cancel()
            if pending_tasks:
                self.server_loop.run_until_complete(
                    asyncio.gather(*pending_tasks, return_exceptions=True)
                )
            self.server_loop.close()
            self.server_loop = None
            self.shutdown_event = None
            self.server_started.clear()
            self.server = None
            self.is_running = False

    async def _async_server(self):
        """Async WebSocket server implementation."""
        self.server = await websockets.serve(self._handle_client, self.host, self.port)
        self.server_started.set()
        logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")
        await self.shutdown_event.wait()

    async def _handle_client(self, websocket, path=None):
        """
        Handle new client connection.

        Args:
            websocket: WebSocket connection
            path: Connection path
        """
        with self.clients_lock:
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
            with self.clients_lock:
                self.clients.discard(websocket)

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
        if not self.is_running or self.server_loop is None or not self.server_started.is_set():
            return

        # Format state for Unity
        unity_message = self._format_for_unity(state)

        # Send to all clients on the server event loop
        future = asyncio.run_coroutine_threadsafe(
            self._broadcast(unity_message),
            self.server_loop
        )
        future.add_done_callback(self._log_broadcast_result)

    async def _broadcast(self, message: Dict):
        """
        Broadcast message to all clients.

        Args:
            message: Message dictionary
        """
        if not self.clients:
            return

        message_json = json.dumps(message)
        with self.clients_lock:
            clients = list(self.clients)

        if not clients:
            return

        results = await asyncio.gather(
            *[client.send(message_json) for client in clients],
            return_exceptions=True
        )
        for client, result in zip(clients, results):
            if isinstance(result, Exception):
                logger.error(f"Error sending Unity state to {client.remote_address}: {result}")
                with self.clients_lock:
                    self.clients.discard(client)

    def _log_broadcast_result(self, future):
        """Log asynchronous broadcast failures."""
        try:
            future.result()
        except Exception as exc:
            logger.error(f"Unity state broadcast failed: {exc}")

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
        if not self.is_running:
            return

        self.is_running = False
        if self.server_loop is not None and self.server_started.is_set():
            shutdown_future = asyncio.run_coroutine_threadsafe(
                self._shutdown_server(),
                self.server_loop
            )
            try:
                shutdown_future.result(timeout=5)
            except Exception as exc:
                logger.error(f"Timed out stopping Unity bridge cleanly: {exc}")

        if self.server_thread is not None:
            self.server_thread.join(timeout=5)
            self.server_thread = None

        logger.info("Unity bridge stopped")

    async def _shutdown_server(self):
        """Close client connections and stop the server loop."""
        with self.clients_lock:
            clients = list(self.clients)

        for client in clients:
            try:
                await client.close()
            except Exception as exc:
                logger.error(f"Error closing Unity client {client.remote_address}: {exc}")

        with self.clients_lock:
            self.clients.clear()

        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        if self.shutdown_event is not None and not self.shutdown_event.is_set():
            self.shutdown_event.set()
