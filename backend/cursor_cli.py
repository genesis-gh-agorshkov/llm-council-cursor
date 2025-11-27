"""Cursor CLI client for making LLM requests."""

import asyncio
import tempfile
import os
import logging
from typing import List, Dict, Any, Optional
from .config import CURSOR_MODEL_MAP, CURSOR_WORKSPACE

# Set up logger
logger = logging.getLogger(__name__)


def messages_to_query(messages: List[Dict[str, str]]) -> str:
    """
    Convert a list of messages to a single query string for Cursor CLI.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
    
    Returns:
        A single query string
    """
    # For now, just use the last user message or combine all messages
    # Cursor CLI expects a single query string
    query_parts = []
    for msg in messages:
        role = msg.get('role', 'user')
        content = msg.get('content', '')
        if role == 'user':
            query_parts.append(content)
        elif role == 'assistant':
            query_parts.append(f"Assistant: {content}")
        elif role == 'system':
            query_parts.append(f"System: {content}")
    
    return "\n\n".join(query_parts)


def map_model_to_cursor(model: str) -> str:
    """
    Map OpenRouter model identifier to Cursor CLI model name.
    
    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-5.1")
    
    Returns:
        Cursor CLI model name (e.g., "gpt-4o")
    """
    # Check if there's a mapping in config
    if model in CURSOR_MODEL_MAP:
        return CURSOR_MODEL_MAP[model]
    
    # Default mapping logic
    # Extract the provider and model name
    if '/' in model:
        provider, model_name = model.split('/', 1)
    else:
        provider = ""
        model_name = model
    
    # Map common models (fallback if not in CURSOR_MODEL_MAP)
    # Using "max" mode models: -high for GPT, -thinking for Claude
    model_mapping = {
        "gpt-5.1": "gpt-5.1-high",  # Max mode
        "gpt-5": "gpt-5-high",  # Max mode
        "gpt-4": "gpt-4o",
        "gpt-4o": "gpt-4o",
        "gemini-3-pro-preview": "gemini-3-pro",
        "gemini-3-pro": "gemini-3-pro",
        "gemini-2.5-flash": "auto",
        "gemini": "auto",
        "claude-opus-4.5": "opus-4.5-thinking",  # Max mode (opus-4.5-high doesn't exist)
        "claude-opus": "opus-4.5-thinking",  # Max mode
        "opus-4.5": "opus-4.5-thinking",  # Max mode
        "opus": "opus-4.5-thinking",  # Max mode
        "claude-sonnet-4.5": "sonnet-4.5-thinking",  # Max mode
        "claude-sonnet": "sonnet-4.5-thinking",  # Max mode
        "sonnet-4": "sonnet-4.5-thinking",  # Max mode
        "grok-4": "grok",
        "grok": "grok",
    }
    
    # Try to find a match
    for key, value in model_mapping.items():
        if key in model_name.lower():
            return value
    
    # Fallback: use the model name as-is (remove provider prefix)
    return model_name.replace(f"{provider}/", "")


async def query_model(
    model: str,
    messages: List[Dict[str, str]],
    timeout: float = 120.0,
    output_dir: Optional[str] = None,
    workspace: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Query a single model via Cursor CLI.

    Args:
        model: OpenRouter model identifier (e.g., "openai/gpt-4o")
        messages: List of message dicts with 'role' and 'content'
        timeout: Request timeout in seconds
        output_dir: Optional directory for output file (if None, uses temp dir)

    Returns:
        Response dict with 'content', or None if failed
    """
    # Map model to Cursor CLI model name
    cursor_model = map_model_to_cursor(model)
    logger.info(f"Querying model {model} (mapped to {cursor_model})")
    
    # Convert messages to query string
    query = messages_to_query(messages)
    logger.debug(f"Query preview (first 100 chars): {query[:100]}...")
    
    # Create output directory if not provided
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="cursor_cli_")
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    # Create a safe filename from model name
    safe_model_name = model.replace("/", "_").replace("\\", "_")
    output_file = os.path.join(output_dir, f"{safe_model_name}.md")
    logger.info(f"Output file: {output_file}")
    
    try:
        # Use stdin to pass the query to avoid shell escaping issues
        # cursor agent --model <model> --print - > output_file
        # Use workspace from parameter, fallback to config, or None
        effective_workspace = workspace or CURSOR_WORKSPACE
        workspace_flag = f' --workspace "{effective_workspace}"' if effective_workspace else ""
        cmd = f'cursor agent --model "{cursor_model}" --print{workspace_flag} - > "{output_file}"'
        logger.info(f"Executing command: {cmd}")
        logger.info(f"Full command details:")
        logger.info(f"  - Model identifier: {model}")
        logger.info(f"  - Cursor model name: {cursor_model}")
        logger.info(f"  - Command: {cmd}")
        logger.info(f"  - Query length: {len(query)} characters")
        logger.info(f"  - Query preview: {query[:200]}...")
        logger.info(f"  - Output file: {output_file}")
        logger.info(f"  - Workspace: {effective_workspace if effective_workspace else '(current directory)'}")
        logger.info(f"  - Timeout: {timeout}s")
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Write query to stdin
        query_bytes = query.encode('utf-8')
        logger.debug(f"Sending {len(query_bytes)} bytes to stdin")
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=query_bytes),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.error(f"Timeout querying model {model} after {timeout}s")
            return None
        
        # Log stdout/stderr even if successful
        if stdout:
            stdout_text = stdout.decode('utf-8', errors='ignore')
            if stdout_text.strip():
                logger.debug(f"stdout from {model}: {stdout_text[:500]}")
        
        if stderr:
            stderr_text = stderr.decode('utf-8', errors='ignore')
            if stderr_text.strip():
                logger.info(f"stderr from {model}: {stderr_text}")
        
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unknown error"
            logger.error(f"Error querying model {model} (returncode {process.returncode}): {error_msg}")
            return None
        
        logger.info(f"Command completed successfully for {model}, returncode: {process.returncode}")
        
        # Read the output file
        if os.path.exists(output_file):
            with open(output_file, 'r', encoding='utf-8') as f:
                content = f.read()
            logger.info(f"Read {len(content)} characters from output file {output_file}")
        else:
            # Fallback to stdout if file doesn't exist
            content = stdout.decode('utf-8', errors='ignore') if stdout else ""
            logger.warning(f"Output file {output_file} does not exist, using stdout instead")
        
        return {
            'content': content.strip(),
            'reasoning_details': None  # Cursor CLI doesn't provide reasoning details
        }
    
    except Exception as e:
        logger.exception(f"Exception querying model {model}: {e}")
        return None


async def query_models_parallel(
    models: List[str],
    messages: List[Dict[str, str]],
    output_dir: Optional[str] = None,
    timeout: float = 180.0,
    workspace: Optional[str] = None
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Query multiple models in parallel using Cursor CLI.

    Args:
        models: List of OpenRouter model identifiers
        messages: List of message dicts to send to each model
        output_dir: Optional directory for output files (if None, uses temp dir)

    Returns:
        Dict mapping model identifier to response dict (or None if failed)
    """
    # Create output directory if not provided
    if output_dir is None:
        output_dir = tempfile.mkdtemp(prefix="cursor_cli_parallel_")
    else:
        os.makedirs(output_dir, exist_ok=True)
    
    # Convert messages to query string once
    query = messages_to_query(messages)
    query_bytes = query.encode('utf-8')
    logger.info(f"Querying {len(models)} models in parallel: {models}")
    logger.debug(f"Query preview (first 100 chars): {query[:100]}...")
    
    # Start all processes in parallel (background)
    processes = []
    model_to_file = {}
    
    for model in models:
        # Map model to Cursor CLI model name
        cursor_model = map_model_to_cursor(model)
        logger.info(f"Starting query for model {model} (mapped to {cursor_model})")
        
        # Create a safe filename from model name
        safe_model_name = model.replace("/", "_").replace("\\", "_")
        output_file = os.path.join(output_dir, f"{safe_model_name}.md")
        model_to_file[model] = output_file
        logger.debug(f"Output file for {model}: {output_file}")
        
        # Build command: cursor agent --model MODEL --print -
        # Capture stdout directly instead of redirecting to file
        # This avoids issues with some models that may not write properly to redirected files
        # Use workspace from parameter, fallback to config, or None
        effective_workspace = workspace or CURSOR_WORKSPACE
        workspace_flag = f' --workspace "{effective_workspace}"' if effective_workspace else ""
        cmd = f'cursor agent --model "{cursor_model}" --print{workspace_flag} -'
        logger.info(f"Executing command for {model}: {cmd}")
        logger.info(f"Full command details for {model}:")
        logger.info(f"  - Model identifier: {model}")
        logger.info(f"  - Cursor model name: {cursor_model}")
        logger.info(f"  - Command: {cmd}")
        logger.info(f"  - Query length: {len(query)} characters")
        logger.info(f"  - Query preview: {query[:200]}...")
        logger.info(f"  - Output file: {output_file}")
        logger.info(f"  - Workspace: {effective_workspace if effective_workspace else '(current directory)'}")
        
        # Start process in background with stdin
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        processes.append((model, process, query_bytes))
    
    logger.info(f"Started {len(processes)} processes, waiting for completion...")
    
    # Wait for all processes to complete in parallel
    async def wait_for_process(model, process, query_bytes):
        """Wait for a single process to complete and return results."""
        try:
            logger.info(f"Waiting for {model} to complete (timeout: {timeout}s)...")
            logger.debug(f"Sending query to {model} ({len(query_bytes)} bytes)")
            
            # Send query to stdin and close it
            try:
                process.stdin.write(query_bytes)
                await process.stdin.drain()
                process.stdin.close()
            except Exception as stdin_error:
                logger.warning(f"Error writing to stdin for {model}: {stdin_error}")
            
            # Read stdout and stderr asynchronously to monitor progress
            stdout_chunks = []
            stderr_chunks = []
            start_time = asyncio.get_event_loop().time()
            
            async def read_stream(stream, chunks_list, stream_name):
                """Read from a stream and collect chunks."""
                try:
                    while True:
                        chunk = await stream.read(4096)  # Read in 4KB chunks
                        if not chunk:
                            break
                        chunks_list.append(chunk)
                        elapsed = asyncio.get_event_loop().time() - start_time
                        total_bytes = sum(len(c) for c in chunks_list)
                        
                        # Show preview of content (first 200 chars of accumulated output)
                        if stream_name == "stdout" and chunks_list:
                            try:
                                accumulated = b''.join(chunks_list).decode('utf-8', errors='ignore')
                                preview = accumulated[:200].replace('\n', '\\n')
                                logger.info(f"{model} {stream_name}: received {len(chunk)} bytes (total: {total_bytes} bytes, elapsed: {elapsed:.1f}s) | Preview: {preview}...")
                            except:
                                logger.info(f"{model} {stream_name}: received {len(chunk)} bytes (total: {total_bytes} bytes, elapsed: {elapsed:.1f}s)")
                        else:
                            logger.info(f"{model} {stream_name}: received {len(chunk)} bytes (total: {total_bytes} bytes, elapsed: {elapsed:.1f}s)")
                except Exception as e:
                    logger.warning(f"Error reading {stream_name} for {model}: {e}")
            
            # Start reading both streams concurrently
            stdout_task = asyncio.create_task(read_stream(process.stdout, stdout_chunks, "stdout"))
            stderr_task = asyncio.create_task(read_stream(process.stderr, stderr_chunks, "stderr"))
            
            # Wait for process to complete
            try:
                returncode = await asyncio.wait_for(process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                # Cancel reading tasks
                stdout_task.cancel()
                stderr_task.cancel()
                raise
            
            # Wait for streams to finish reading
            await stdout_task
            await stderr_task
            
            # Combine chunks
            stdout = b''.join(stdout_chunks) if stdout_chunks else b''
            stderr = b''.join(stderr_chunks) if stderr_chunks else b''
            
            elapsed = asyncio.get_event_loop().time() - start_time
            logger.info(f"{model} completed: returncode={returncode}, stdout={len(stdout)} bytes, stderr={len(stderr)} bytes, elapsed={elapsed:.1f}s")
            
            # Log stderr if there's an error
            if returncode != 0:
                stderr_text = stderr.decode('utf-8', errors='ignore') if stderr else ''
                logger.error(f"{model} failed with returncode {returncode}")
                if stderr_text:
                    logger.error(f"{model} stderr: {stderr_text[:500]}")  # First 500 chars
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore')
                    logger.error(f"{model} stdout (partial): {stdout_text[:500]}")
            
            return (model, process, stdout, stderr, None)
        except asyncio.TimeoutError:
            logger.error(f"Timeout waiting for {model} after {timeout}s - killing process")
            try:
                # Try to get any partial output before killing
                try:
                    if process.stdin and not process.stdin.is_closing():
                        process.stdin.close()
                except:
                    pass
                
                # Try to read any remaining stdout/stderr before killing
                partial_stdout = b''
                partial_stderr = b''
                try:
                    if process.stdout:
                        partial_stdout = await asyncio.wait_for(process.stdout.read(), timeout=1.0)
                    if process.stderr:
                        partial_stderr = await asyncio.wait_for(process.stderr.read(), timeout=1.0)
                except:
                    pass
                
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5.0)
                
                # Log partial output
                if partial_stdout:
                    logger.warning(f"{model} partial stdout after timeout: {len(partial_stdout)} bytes")
                    stdout_text = partial_stdout.decode('utf-8', errors='ignore')
                    logger.warning(f"{model} partial stdout content: {stdout_text[:500]}")
                if partial_stderr:
                    logger.warning(f"{model} partial stderr after timeout: {len(partial_stderr)} bytes")
                    stderr_text = partial_stderr.decode('utf-8', errors='ignore')
                    logger.warning(f"{model} partial stderr content: {stderr_text[:500]}")
            except Exception as kill_error:
                logger.warning(f"Error killing process for {model}: {kill_error}")
            return (model, process, None, None, TimeoutError(f"Timeout after {timeout}s"))
        except Exception as e:
            logger.exception(f"Exception waiting for {model}: {e}")
            return (model, process, None, None, e)
    
    # Wait for all processes in parallel
    tasks = [wait_for_process(model, process, query_bytes) for model, process, query_bytes in processes]
    completed = await asyncio.gather(*tasks)
    
    # Process results
    results = {}
    for model, process, stdout, stderr, error in completed:
        try:
            if error:
                error_msg = str(error)
                logger.error(f"Error waiting for {model}: {error_msg}")
                
                # Log stderr if available
                if stderr:
                    stderr_text = stderr.decode('utf-8', errors='ignore') if isinstance(stderr, bytes) else str(stderr)
                    if stderr_text:
                        logger.error(f"{model} stderr content: {stderr_text[:1000]}")
                
                # Log stdout if available (might contain error info)
                if stdout:
                    stdout_text = stdout.decode('utf-8', errors='ignore') if isinstance(stdout, bytes) else str(stdout)
                    if stdout_text:
                        logger.error(f"{model} stdout content: {stdout_text[:1000]}")
                
                # Write error info to file for debugging
                output_file = model_to_file.get(model)
                if output_file:
                    try:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"ERROR: {error_msg}\n\n")
                            if stderr:
                                stderr_text = stderr.decode('utf-8', errors='ignore') if isinstance(stderr, bytes) else str(stderr)
                                if stderr_text:
                                    f.write(f"Stderr:\n{stderr_text}\n\n")
                            if stdout:
                                stdout_text = stdout.decode('utf-8', errors='ignore') if isinstance(stdout, bytes) else str(stdout)
                                if stdout_text:
                                    f.write(f"Stdout:\n{stdout_text}\n")
                        logger.info(f"Wrote error info to {output_file}")
                    except Exception as write_error:
                        logger.warning(f"Failed to write error file for {model}: {write_error}")
                results[model] = None
                continue
            
            # Check return code
            if process.returncode != 0:
                stderr_text = stderr.decode('utf-8', errors='ignore') if stderr else ''
                stdout_text = stdout.decode('utf-8', errors='ignore') if stdout else ''
                logger.error(f"Error running Cursor CLI for model {model} (returncode {process.returncode}): {stderr_text[:200] if stderr_text else 'Unknown error'}")
                logger.error(f"{model} full stderr: {stderr_text}")
                logger.error(f"{model} full stdout: {stdout_text}")
                # Write error to file
                output_file = model_to_file.get(model)
                if output_file:
                    try:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(f"ERROR: Process exited with returncode {process.returncode}\n\n")
                            if stderr_text:
                                f.write(f"Stderr:\n{stderr_text}\n\n")
                            if stdout_text:
                                f.write(f"Stdout:\n{stdout_text}\n")
                        logger.info(f"Wrote error info to {output_file}")
                    except Exception as write_error:
                        logger.warning(f"Failed to write error file for {model}: {write_error}")
                results[model] = None
                continue
            
            logger.info(f"Process {model} finished with returncode: {process.returncode}")
            
            # Log stdout/stderr - always log, not just if non-empty
            # Note: stdout will be empty because we redirect to file with >
            if stdout:
                stdout_text = stdout.decode('utf-8', errors='ignore')
                if stdout_text.strip():
                    logger.info(f"stdout from {model} ({len(stdout_text)} chars): {stdout_text[:500]}{'...' if len(stdout_text) > 500 else ''}")
                else:
                    logger.debug(f"stdout from {model}: (empty - expected, output redirected to file)")
            else:
                logger.debug(f"stdout from {model}: (empty - expected, output redirected to file)")
            
            if stderr:
                stderr_text = stderr.decode('utf-8', errors='ignore')
                if stderr_text.strip():
                    logger.info(f"stderr from {model} ({len(stderr_text)} chars): {stderr_text}")
                else:
                    logger.debug(f"stderr from {model}: (empty)")
            else:
                logger.debug(f"stderr from {model}: (empty)")
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore') if stderr else "Unknown error"
                logger.error(f"Error running Cursor CLI for model {model} (returncode {process.returncode}): {error_msg}")
                results[model] = None
            else:
                logger.info(f"Command completed successfully for {model}, returncode: {process.returncode}")
                
                # Get content from stdout (primary source)
                content = ""
                if stdout:
                    stdout_content = stdout.decode('utf-8', errors='ignore')
                    if stdout_content.strip():
                        logger.info(f"Using stdout content for {model} ({len(stdout_content)} chars)")
                        content = stdout_content
                
                # Fallback to stderr if stdout is empty (sometimes output goes there)
                if not content.strip() and stderr:
                    stderr_content = stderr.decode('utf-8', errors='ignore')
                    if stderr_content.strip():
                        # Check if stderr looks like actual output (not an error message)
                        if not any(err in stderr_content.lower() for err in ['error', 'failed', 'cannot', 'invalid']):
                            logger.info(f"Using stderr content for {model} ({len(stderr_content)} chars) - appears to be output")
                            content = stderr_content
                        else:
                            logger.warning(f"stderr contains error message: {stderr_content[:200]}")
                
                # Also write to file for debugging/backup
                output_file = model_to_file[model]
                if content.strip():
                    try:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(content)
                        logger.debug(f"Wrote {len(content)} characters to output file {output_file}")
                    except Exception as e:
                        logger.warning(f"Failed to write to output file {output_file}: {e}")
                
                if not content.strip():
                    logger.error(f"No content received for {model} - stdout and stderr are both empty!")
                    logger.error(f"  - Return code: {process.returncode}")
                    results[model] = None
                else:
                    results[model] = {
                        'content': content.strip(),
                        'reasoning_details': None
                    }
                    logger.info(f"Successfully processed {model}: {len(content.strip())} characters")
        except Exception as e:
            logger.exception(f"Exception in parallel query for model {model}: {e}")
            results[model] = None
    
    logger.info(f"Completed parallel queries. Results: {sum(1 for r in results.values() if r is not None)}/{len(models)} successful")
    return results



