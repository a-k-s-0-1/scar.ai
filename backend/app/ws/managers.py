"""WebSocket connection manager for broadcasting live session state."""

from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from app.utils.logger import logger

EventRecorder = Callable[[str, dict[str, Any]], Awaitable[int | None]]


class ConnectionManager:
    """Manages active WebSocket connections grouped by research session ID."""

    def __init__(self) -> None:
        # Mapping of session_id to list of connected WebSockets
        self.active_connections: dict[str, list[WebSocket]] = defaultdict(list)
        # Durable recorder injected at startup: every broadcast is persisted so a
        # finished session can still be replayed. Optional so the manager works
        # standalone in tests and without a database.
        self._event_recorder: EventRecorder | None = None

    def set_event_recorder(self, recorder: EventRecorder | None) -> None:
        """Install the durable event writer used by :meth:`broadcast`."""
        self._event_recorder = recorder

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        """Accept incoming connection and store in active connections list."""
        await websocket.accept()
        self.active_connections[session_id].append(websocket)
        logger.info(
            f"WebSocket client connected to session '{session_id}'. Total: {len(self.active_connections[session_id])}"
        )

    def disconnect(self, websocket: WebSocket, session_id: str) -> None:
        """Remove disconnected socket."""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        logger.info(f"WebSocket client disconnected from session '{session_id}'.")

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        """Persist then broadcast a message to every client of a session.

        Persisting first (and regardless of who is connected) is what makes the
        event log complete: a run nobody was watching still replays later, and
        the sequence number stamped on the message lets a client that already
        replayed history skip duplicates when the live socket catches up.
        """
        if self._event_recorder is not None:
            seq = await self._event_recorder(session_id, message)
            if seq is not None:
                message = {**message, "seq": seq}

        if session_id not in self.active_connections:
            return

        dead_connections: list[WebSocket] = []
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(
                    f"Error sending message to client in session {session_id}: {e}"
                )
                dead_connections.append(connection)

        # Cleanup dead sockets
        for dead in dead_connections:
            self.disconnect(dead, session_id)


ws_manager = ConnectionManager()
