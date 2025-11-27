"""FastAPI backend for LLM Council."""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uuid
import json
import asyncio
import logging
import os
from pathlib import Path

from . import storage
from .council import run_full_council, generate_conversation_title, stage1_collect_responses, stage2_collect_rankings, stage3_synthesize_final, calculate_aggregate_rankings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="LLM Council API")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""
    pass


class SendMessageRequest(BaseModel):
    """Request to send a message in a conversation."""
    content: str
    workspace: Optional[str] = None  # Optional workspace override


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]
    workspace: Optional[str] = None


class SetWorkspaceRequest(BaseModel):
    """Request to set workspace for a conversation."""
    workspace: Optional[str] = None


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""
    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())
    conversation = storage.create_conversation(conversation_id)
    return conversation


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.get("/api/workspaces")
async def list_workspaces():
    """
    List available workspace directories one level up from server's working directory.
    Returns list of directory paths.
    """
    try:
        # Get the server's current working directory
        server_dir = os.getcwd()
        parent_dir = os.path.dirname(server_dir)
        
        logger.info(f"Listing workspaces in parent directory: {parent_dir}")
        
        # List all directories in the parent directory
        workspaces = []
        if os.path.exists(parent_dir) and os.path.isdir(parent_dir):
            for item in os.listdir(parent_dir):
                item_path = os.path.join(parent_dir, item)
                if os.path.isdir(item_path):
                    workspaces.append({
                        "path": item_path,
                        "name": item
                    })
        
        # Sort by name
        workspaces.sort(key=lambda x: x["name"])
        
        logger.info(f"Found {len(workspaces)} workspace directories")
        return {"workspaces": workspaces, "parent_dir": parent_dir}
    except Exception as e:
        logger.exception(f"Error listing workspaces: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list workspaces: {str(e)}")


@app.put("/api/conversations/{conversation_id}/workspace")
async def set_conversation_workspace(conversation_id: str, request: SetWorkspaceRequest):
    """Set the workspace directory for a conversation."""
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Validate workspace path if provided
    if request.workspace:
        if not os.path.exists(request.workspace):
            raise HTTPException(status_code=400, detail=f"Workspace path does not exist: {request.workspace}")
        if not os.path.isdir(request.workspace):
            raise HTTPException(status_code=400, detail=f"Workspace path is not a directory: {request.workspace}")
    
    storage.update_conversation_workspace(conversation_id, request.workspace)
    logger.info(f"Set workspace for conversation {conversation_id}: {request.workspace}")
    
    updated_conversation = storage.get_conversation(conversation_id)
    return updated_conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and run the 3-stage council process.
    Returns the complete response with all stages.
    """
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0
    
    # Get workspace from request or conversation
    workspace = request.workspace or conversation.get("workspace")
    
    # Update workspace if provided in request
    if request.workspace is not None:
        storage.update_conversation_workspace(conversation_id, request.workspace)

    # Add user message
    storage.add_user_message(conversation_id, request.content)

    # If this is the first message, generate a title
    if is_first_message:
        title = await generate_conversation_title(request.content, workspace=workspace)
        storage.update_conversation_title(conversation_id, title)

    # Run the 3-stage council process
    stage1_results, stage2_results, stage3_result, metadata = await run_full_council(
        request.content, workspace=workspace
    )

    # Add assistant message with all stages
    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result
    )

    # Return the complete response with metadata
    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(conversation_id: str, request: SendMessageRequest):
    """
    Send a message and stream the 3-stage council process.
    Returns Server-Sent Events as each stage completes.
    """
    logger.info(f"Received stream request for conversation {conversation_id}")
    logger.info(f"Message content (first 100 chars): {request.content[:100]}...")
    
    # Check if conversation exists
    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        logger.error(f"Conversation {conversation_id} not found")
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Check if this is the first message
    is_first_message = len(conversation["messages"]) == 0
    logger.info(f"Is first message: {is_first_message}")
    
    # Get workspace from request or conversation
    workspace = request.workspace or conversation.get("workspace")
    if workspace:
        logger.info(f"Using workspace: {workspace}")
    else:
        logger.info("No workspace specified, using default")

    async def event_generator():
        try:
            # Add user message
            logger.info("Adding user message to conversation")
            storage.add_user_message(conversation_id, request.content)
            
            # Update workspace if provided in request
            if request.workspace is not None:
                storage.update_conversation_workspace(conversation_id, request.workspace)

            # Start title generation in parallel (don't await yet)
            title_task = None
            if is_first_message:
                logger.info("Starting title generation task")
                title_task = asyncio.create_task(generate_conversation_title(request.content, workspace=workspace))

            # Stage 1: Collect responses
            logger.info("Starting Stage 1: Collecting responses")
            yield f"data: {json.dumps({'type': 'stage1_start'})}\n\n"
            stage1_results = await stage1_collect_responses(request.content, workspace=workspace)
            logger.info(f"Stage 1 completed with {len(stage1_results)} results")
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            # Stage 2: Collect rankings
            logger.info("Starting Stage 2: Collecting rankings")
            yield f"data: {json.dumps({'type': 'stage2_start'})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(request.content, stage1_results, workspace=workspace)
            aggregate_rankings = calculate_aggregate_rankings(stage2_results, label_to_model)
            logger.info(f"Stage 2 completed with {len(stage2_results)} rankings")
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            # Stage 3: Synthesize final answer
            logger.info("Starting Stage 3: Synthesizing final answer")
            yield f"data: {json.dumps({'type': 'stage3_start'})}\n\n"
            stage3_result = await stage3_synthesize_final(request.content, stage1_results, stage2_results, workspace=workspace)
            logger.info("Stage 3 completed")
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            # Wait for title generation if it was started
            if title_task:
                logger.info("Waiting for title generation")
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                logger.info(f"Title generated: {title}")
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            # Save complete assistant message
            logger.info("Saving assistant message to conversation")
            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result
            )

            # Send completion event
            logger.info("Stream completed successfully")
            yield f"data: {json.dumps({'type': 'complete'})}\n\n"

        except Exception as e:
            logger.exception(f"Error in stream event generator: {e}")
            # Send error event
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
