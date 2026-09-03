from fastapi import APIRouter, Security, HTTPException, Body, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
import re
from common.auth import azure_scheme, scopes
from common.log import logger
from common.role_based_access import required_roles
from common.socket import ConnectionManager

api_router = APIRouter()

# Defense-in-depth on the chat broadcast surface: drop messages that paste a
# JWT-shaped token so it doesn't get fanned out to every connected client.
# Authentication itself is already enforced upstream in
# ConnectionManager.auth_connect(); this only stops the body of a chat
# message from echoing a raw token to the room.
#
# A JWT has three base64url segments separated by dots. The first two
# segments (header + payload) always start with "eyJ" because they are
# JSON objects whose first character ("{") encodes to that prefix in
# base64url. The third segment is the signature with no fixed prefix, so
# we only constrain it to base64url characters.
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)

def contains_jwt(text: str) -> bool:
    """Return True if `text` contains a JWT-shaped substring.

    Catches the common case of a user pasting a real JWT (optionally with a
    `Bearer ` prefix or wrapped in surrounding prose) into a chat message.
    This is a heuristic — it matches the standard three-segment base64url
    shape but cannot catch every possible encoding. Authentication of the
    WebSocket connection itself is already enforced upstream in
    ConnectionManager.auth_connect().
    """
    return bool(_JWT_PATTERN.search(text))

@api_router.get("/user-data")
async def get_user_data(token=Security(azure_scheme, scopes=scopes)):
    logger.info("User Api - Returning User data")
    return {"message": "Hello from API"}

# Define model for request body
class AdminDataRequest(BaseModel):
    message: str = "Default message"
    status: int = 200

# Changed from GET to POST and using request body
@api_router.post("/admin-data")
@required_roles(["Admin"])
async def get_admin_data(request: AdminDataRequest = Body(...), token=Security(azure_scheme, scopes=scopes)):
    logger.info(f"Admin API - Message: {request.message}, Status: {request.status}")
    
    # You can use the status parameter to simulate different responses
    if request.status >= 400:
        raise HTTPException(status_code=request.status, detail=request.message)
        
    return {
        "message": f"Hello Admin: {request.message}",
        "status": request.status,
        "received": True
    }

# Create a manager instance with appropriate role configuration
chatConnectionManager = ConnectionManager(
    receiver_roles=[],  # Empty means anyone can connect
    sender_roles=[]     # Empty means anyone can send messages
)

# WebSocket endpoint
@api_router.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    try:
        # Connect with authentication - no required_roles parameter (defined in constructor)
        await chatConnectionManager.auth_connect(websocket)
        
        try:
            while True:
                data = await websocket.receive_text()
                user_name = websocket.state.user.get("name", "Unknown User")

                # Suppress broadcast of messages that look like a raw JWT.
                # Replaces the previous `in data.lower()` substring check,
                # which dropped legitimate plain-English messages ("the
                # token bucket is full") while letting real JWTs through
                # ("Bearer eyJ..."). See issue #140 for the reasoning.
                if contains_jwt(data):
                    # Send private warning
                    await chatConnectionManager.send_personal_message(
                        "!!! Security warning: Authentication data should not be sent in chat messages !!!",
                        websocket
                    )
                    continue  # Skip further processing of this message

                # Send personal acknowledgment using send_personal_message (unchanged)
                await chatConnectionManager.send_personal_message(f"You sent: {data}", websocket)
                
                # Fix: Wrap the data in a dictionary with a "content" field
                await chatConnectionManager.broadcast(
                    data={"content": f"{user_name}: {data}"},
                    type="message",
                    sender_websocket=websocket,
                    skip_self=True  # Don't send to the sender
                )
        except WebSocketDisconnect:
            chatConnectionManager.disconnect(websocket)
            user_name = websocket.state.user.get("name", "Unknown User")
            
            # Broadcast leave message using the new format
            await chatConnectionManager.broadcast(
                data={"content": f"{user_name} left the chat"},
                type="message"
            )
            
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        if websocket in chatConnectionManager.active_connections:
            chatConnectionManager.disconnect(websocket)