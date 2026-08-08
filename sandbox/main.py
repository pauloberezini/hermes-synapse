from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import jupyter_client
import queue
import time
import os
import re

app = FastAPI()

km = None
kc = None

class CodeRequest(BaseModel):
    code: str
    timeout: float = 120.0

class CodeResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    display_data: list
    error: str | None = None

@app.on_event("startup")
def startup_event():
    global km, kc
    # Ensure working directory is the shared volume if it exists, otherwise /app
    if os.path.exists("/mnt/data"):
        os.chdir("/mnt/data")
    
    km = jupyter_client.KernelManager()
    km.start_kernel()
    kc = km.client()
    kc.start_channels()
    kc.wait_for_ready(timeout=10)
    
    # Pre-configure matplotlib inline
    run_code_internal("%matplotlib inline")

@app.on_event("shutdown")
def shutdown_event():
    global km
    if km:
        km.shutdown_kernel()

def remove_ansi_escape_sequences(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def run_code_internal(code: str, timeout: float = 120.0):
    global kc, km
    if not kc:
        raise Exception("Kernel is not ready")
        
    msg_id = kc.execute(code)
    stdout = []
    stderr = []
    display_data = []
    has_error = False
    
    start_time = time.time()
    
    while True:
        if time.time() - start_time > timeout:
            km.interrupt_kernel()
            return False, "".join(stdout), "".join(stderr) + "\nExecution timed out.", display_data

        try:
            msg = kc.get_iopub_msg(timeout=1)
            msg_type = msg['header']['msg_type']
            content = msg['content']
            
            # Match the msg_id to ensure we only collect responses for our request
            if msg.get("parent_header", {}).get("msg_id") != msg_id:
                continue

            if msg_type == 'stream':
                if content['name'] == 'stdout':
                    stdout.append(content['text'])
                elif content['name'] == 'stderr':
                    stderr.append(content['text'])
            elif msg_type == 'display_data' or msg_type == 'execute_result':
                display_data.append(content['data'])
            elif msg_type == 'error':
                traceback = "\n".join(content.get('traceback', []))
                stderr.append(remove_ansi_escape_sequences(traceback))
                has_error = True
            elif msg_type == 'status' and content['execution_state'] == 'idle':
                # Execution finished
                break
        except queue.Empty:
            continue
            
    return not has_error, "".join(stdout), "".join(stderr), display_data

@app.post("/execute", response_model=CodeResponse)
def execute_code_endpoint(req: CodeRequest):
    try:
        success, stdout, stderr, display_data = run_code_internal(req.code, timeout=req.timeout)
        return CodeResponse(
            success=success,
            stdout=stdout,
            stderr=stderr,
            display_data=display_data
        )
    except Exception as e:
        return CodeResponse(
            success=False,
            stdout="",
            stderr="",
            display_data=[],
            error=str(e)
        )
