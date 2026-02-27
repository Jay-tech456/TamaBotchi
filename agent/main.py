"""
TamaBotchi Agent API Server
FastAPI server exposing the AI agent functionality
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime
import uvicorn
import logging
import traceback

logger = logging.getLogger(__name__)

from config import Config
from core.agent import TamaBotchiAgent
from tools.mcp_client import MCPClient
import conversation_store

# Validate config on startup
Config.validate()

app = FastAPI(
    title="TamaBotchi Agent API",
    version="1.0.0",
    description="TamaBotchi iMessage AI agent"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active agents (in production, use proper state management)
active_agents: Dict[str, TamaBotchiAgent] = {}


# Pydantic models
class UserDetectedRequest(BaseModel):
    user_id: str
    other_user_id: str
    context: Dict


class IncomingMessageRequest(BaseModel):
    user_id: str
    sender_id: str
    message: str
    conversation_id: str


class SendMessageRequest(BaseModel):
    user_id: str
    recipient_id: str
    message: str


class TaskRequest(BaseModel):
    user_id: str
    task: str


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    services: Dict[str, bool]


def get_or_create_agent(user_id: str) -> TamaBotchiAgent:
    """Get existing agent or create new one for user"""
    if user_id not in active_agents:
        active_agents[user_id] = TamaBotchiAgent(user_id)
    return active_agents[user_id]


@app.get('/health', response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    mcp_client = MCPClient()

    # Check service health
    services = {
        'agent': True,
        'mcp': False,  # Will implement actual check
        'imessage': False,
    }

    # Try to check iMessage server
    try:
        from tools.imessage_tool import iMessageTool
        imsg = iMessageTool()
        services['imessage'] = imsg.health_check()
    except Exception:
        services['imessage'] = False

    return HealthResponse(
        status='healthy' if services['agent'] else 'degraded',
        timestamp=datetime.now().isoformat(),
        services=services
    )


@app.post('/users/{user_id}/detected')
async def user_detected(user_id: str, request: UserDetectedRequest, background_tasks: BackgroundTasks):
    """
    Handle when another user is detected nearby

    This is called by the proximity detection service when someone with the app
    comes into range at an event.
    """
    try:
        agent = get_or_create_agent(user_id)

        # Handle the detection
        result = agent.handle_new_person_nearby(
            request.other_user_id,
            request.context
        )

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/users/{user_id}/messages/incoming')
async def incoming_message(user_id: str, request: IncomingMessageRequest):
    """
    Handle an incoming message for a user

    This is called when someone responds to the agent
    """
    try:
        conversation_store.log_message(
            sender=request.sender_id,
            message=request.message,
            is_from_agent=False,
            conversation_id=request.conversation_id,
        )

        agent = get_or_create_agent(user_id)

        result = agent.handle_incoming_message(
            request.sender_id,
            request.message,
            request.conversation_id
        )

        if result.get("response"):
            conversation_store.log_message(
                sender=request.sender_id,
                message=result["response"],
                is_from_agent=True,
                conversation_id=request.conversation_id,
            )

        return result

    except Exception as e:
        logger.error("Error in incoming_message: %s\n%s", e, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/users/{user_id}/messages/send')
async def send_message(user_id: str, request: SendMessageRequest):
    """
    Send a message on behalf of a user

    This is called when the user manually wants to send a message through the agent
    """
    try:
        agent = get_or_create_agent(user_id)

        # Get recipient profile to determine contact method
        recipient_profile = agent.mcp_client.get_user_profile(request.recipient_id)

        if not recipient_profile:
            raise HTTPException(status_code=404, detail="Recipient not found")

        phone = recipient_profile.get('contact', {}).get('phone')

        if not phone:
            raise HTTPException(status_code=400, detail="Recipient has no phone number")

        send_result = agent.imessage_tool.send_message(phone, request.message)
        result = {
            'method': 'imessage',
            'success': send_result.get('success', False)
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/users/{user_id}/task')
async def execute_task(user_id: str, request: TaskRequest):
    """
    Execute a general task for the user

    This allows the agent to be used for arbitrary tasks
    """
    try:
        agent = get_or_create_agent(user_id)
        result = agent.run(request.task)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get('/users/{user_id}/profile')
async def get_user_profile(user_id: str):
    """Get user's profile"""
    mcp_client = MCPClient()
    profile = mcp_client.get_user_profile(user_id)

    if not profile:
        raise HTTPException(status_code=404, detail="User not found")

    return profile


@app.patch('/users/{user_id}/profile')
async def update_user_profile(user_id: str, data: Dict):
    """Update user's profile"""
    mcp_client = MCPClient()
    success = mcp_client.update_user_profile(user_id, data)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update profile")

    return {"success": True}


@app.get('/users/{user_id}/preferences')
async def get_user_preferences(user_id: str):
    """Get user's preferences"""
    mcp_client = MCPClient()
    preferences = mcp_client.get_user_preferences(user_id)
    return preferences


@app.patch('/users/{user_id}/preferences')
async def update_user_preferences(user_id: str, preferences: Dict):
    """Update user's preferences"""
    mcp_client = MCPClient()
    success = mcp_client.update_user_preferences(user_id, preferences)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to update preferences")

    return {"success": True}


@app.get('/users/{user_id}/conversations/{conversation_id}')
async def get_conversation(user_id: str, conversation_id: str, limit: int = 50):
    """Get conversation history"""
    mcp_client = MCPClient()
    messages = mcp_client.get_conversation_history(conversation_id, limit)

    return {
        'conversation_id': conversation_id,
        'messages': messages,
        'count': len(messages)
    }


# ── Desktop Pet Endpoints ──────────────────────────────────────────────

@app.get('/pet/conversations')
async def pet_get_conversations():
    """Return all tracked conversations for the desktop pet."""
    convos = conversation_store.get_all_conversations()
    return {
        "conversations": list(convos.values()),
        "unread_count": conversation_store.get_unread_count(),
    }


@app.get('/pet/conversations/unread')
async def pet_get_unread():
    """Return only unread conversations."""
    convos = conversation_store.get_unread_conversations()
    return {
        "conversations": list(convos.values()),
        "unread_count": len(convos),
    }


@app.get('/pet/conversations/unread/count')
async def pet_unread_count():
    """Quick count of unread conversations for the notification badge."""
    return {"unread_count": conversation_store.get_unread_count()}


@app.post('/pet/conversations/{conversation_id}/read')
async def pet_mark_read(conversation_id: str):
    """Mark a conversation as read."""
    conversation_store.mark_read(conversation_id)
    return {"success": True}


@app.post('/pet/conversations/read-all')
async def pet_mark_all_read():
    """Mark all conversations as read."""
    conversation_store.mark_all_read()
    return {"success": True}


@app.post('/pet/conversations/{conversation_id}/summarize')
async def pet_summarize_conversation(conversation_id: str):
    """Use Claude to generate a comprehensive summary for a single conversation."""
    convos = conversation_store.get_all_conversations()
    convo = convos.get(conversation_id)
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages_text = "\n".join(
        f"{'[AGENT]' if m['from'] == 'agent' else '[' + m['from'] + ']'}: {m['text']}"
        for m in convo.get("messages", [])
    )

    from anthropic import Anthropic
    client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
    resp = client.messages.create(
        model=Config.CLAUDE_MODEL,
        max_tokens=1024,
        system="You are a concise assistant. Produce a structured JSON summary of this iMessage conversation. Return ONLY valid JSON with these keys: who (string - who contacted), intent (string - what do they want), requirements (array of strings - specific requirements/asks), urgency (low/medium/high), sentiment (positive/neutral/negative), action_items (array of strings), one_liner (string - 1 sentence summary).",
        messages=[{"role": "user", "content": f"Summarize this conversation:\n\n{messages_text}"}],
    )

    import json as _json
    raw = resp.content[0].text.strip()
    try:
        summary = _json.loads(raw)
    except _json.JSONDecodeError:
        summary = {"one_liner": raw, "who": convo["sender"], "intent": "unknown", "requirements": [], "urgency": "medium", "sentiment": "neutral", "action_items": []}

    conversation_store.update_summary(conversation_id, summary)
    return {"summary": summary}


@app.post('/pet/summarize-all')
async def pet_summarize_all():
    """Generate summaries for every conversation that does not yet have one."""
    convos = conversation_store.get_all_conversations()
    summaries = {}
    for cid, convo in convos.items():
        if convo.get("summary"):
            summaries[cid] = convo["summary"]
            continue
        messages_text = "\n".join(
            f"{'[AGENT]' if m['from'] == 'agent' else '[' + m['from'] + ']'}: {m['text']}"
            for m in convo.get("messages", [])
        )
        from anthropic import Anthropic
        client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model=Config.CLAUDE_MODEL,
            max_tokens=1024,
            system="You are a concise assistant. Produce a structured JSON summary of this iMessage conversation. Return ONLY valid JSON with these keys: who (string - who contacted), intent (string - what do they want), requirements (array of strings - specific requirements/asks), urgency (low/medium/high), sentiment (positive/neutral/negative), action_items (array of strings), one_liner (string - 1 sentence summary).",
            messages=[{"role": "user", "content": f"Summarize this conversation:\n\n{messages_text}"}],
        )
        import json as _json
        raw = resp.content[0].text.strip()
        try:
            summary = _json.loads(raw)
        except _json.JSONDecodeError:
            summary = {"one_liner": raw, "who": convo["sender"], "intent": "unknown", "requirements": [], "urgency": "medium", "sentiment": "neutral", "action_items": []}
        conversation_store.update_summary(cid, summary)
        summaries[cid] = summary

    return {"summaries": summaries, "count": len(summaries)}


if __name__ == '__main__':
    print("🚀 Starting TamaBotchi Agent API...")
    print(f"📍 Agent: {Config.AGENT_NAME}")
    print(f"🔗 iMessage Server: {Config.IMESSAGE_SERVER_URL}")
    print(f"🔗 MCP Server: {Config.MCP_SERVER_URL}")
    print("")

    uvicorn.run(
        app,
        host='0.0.0.0',
        port=5000,
        log_level='info'
    )
