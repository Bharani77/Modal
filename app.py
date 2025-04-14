import gradio as gr
import subprocess
import os
import tempfile
import shutil
import json
import re
import time
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from typing import List, Callable

# Modal token and secret (replace with environment variables in production)
MODAL_TOKEN_ID = os.environ.get("MODAL_TOKEN_ID", "ak-VPIrJKnuj04h8zpLJrkMdB")
MODAL_TOKEN_SECRET = os.environ.get("MODAL_TOKEN_SECRET", "as-XX7bnxLKcEyy1udFdmye4x")

# Explicitly define allowed domains
ALLOWED_DOMAINS = [
    "galaxykicklock.web.app",
    "lightning.ai"
]

# Create the FastAPI app
app = FastAPI()

# Rate limiting middleware
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_limit=30, time_window=60):
        super().__init__(app)
        self.requests = defaultdict(list)
        self.requests_limit = requests_limit
        self.time_window = time_window
        
    async def dispatch(self, request: Request, call_next):
        # Get client IP
        client_ip = request.client.host
        
        # Clean old requests
        current_time = time.time()
        self.requests[client_ip] = [req_time for req_time in self.requests[client_ip] 
                                   if current_time - req_time < self.time_window]
        
        # Check if rate limit exceeded
        if len(self.requests[client_ip]) >= self.requests_limit:
            return JSONResponse(
                status_code=429,
                content={"error": "Too many requests", "message": "Rate limit exceeded. Try again later."}
            )
            
        # Add current request time
        self.requests[client_ip].append(current_time)
        
        # Process request
        response = await call_next(request)
        return response

# Custom domain restriction middleware class
class DomainRestrictionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, allowed_domains: List[str]):
        super().__init__(app)
        self.allowed_domains = allowed_domains

    async def dispatch(self, request: Request, call_next):
        # Get origin and referer headers
        origin = request.headers.get("Origin", "")
        referer = request.headers.get("Referer", "")
        
        # Extract domains from headers
        origin_domain = self._extract_domain(origin) if origin else ""
        referer_domain = self._extract_domain(referer) if referer else ""
        
        # For command-line tools like curl, these might be empty or spoofed
        # Block if not from allowed domains (no exceptions for development)
        if origin_domain not in self.allowed_domains and referer_domain not in self.allowed_domains:
            # Log attempted access for monitoring
            print(f"Access denied: Origin: {origin}, Referer: {referer}, IP: {request.client.host}")
            
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access denied",
                    "message": "This service can only be accessed from authorized domains."
                }
            )
        
        # If allowed, proceed with the request
        response = await call_next(request)
        return response
    
    def _extract_domain(self, url: str) -> str:
        """Extract the domain from a URL without protocol, path, or port."""
        if not url:
            return ""
            
        # Remove protocol
        if "://" in url:
            url = url.split("://")[1]
        
        # Remove path and query parameters
        if "/" in url:
            url = url.split("/")[0]
            
        # Remove port if present
        if ":" in url:
            url = url.split(":")[0]
            
        return url

# Anti-automation middleware to block common API clients
class AntiAutomationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Skip check for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Check for common API client user agents
        user_agent = request.headers.get("User-Agent", "").lower()
        
        # Block common automation tools
        blocked_agents = ["curl", "wget", "postman", "insomnia", "python-requests", "httpie"]
        if any(agent in user_agent for agent in blocked_agents):
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied", "message": "API client tools not allowed"}
            )
            
        # Additional header checks
        # Legitimate browsers typically send these headers
        if not request.headers.get("Accept-Language") and not request.headers.get("Accept"):
            return JSONResponse(
                status_code=403,
                content={"error": "Access denied", "message": "Missing required headers"}
            )
            
        # Proceed with the request
        response = await call_next(request)
        return response

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; connect-src *; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "same-origin"
        
        return response

# Add middlewares in the correct order
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_limit=30, time_window=60)  # 30 requests per minute
app.add_middleware(AntiAutomationMiddleware)
app.add_middleware(
    DomainRestrictionMiddleware, 
    allowed_domains=ALLOWED_DOMAINS
)

# Create data models for the requests
class DeployRequest(BaseModel):
    repo_url: str
    modal_name: str = "default_app"  # Default value if not provided

class StatusRequest(BaseModel):
    modal_name: str

class UndeployRequest(BaseModel):
    modal_name: str

# Dictionary to store deployment status
deployment_status = {}

# Helper function to set environment variables for Modal
def get_modal_env(modal_name):
    env = os.environ.copy()
    env["MODAL_APP_NAME"] = modal_name
    env["MODAL_TOKEN_ID"] = MODAL_TOKEN_ID
    env["MODAL_TOKEN_SECRET"] = MODAL_TOKEN_SECRET
    return env

# Function to handle deployment
# Add this constant at the top of your file with the other constants
HARDCODED_REPO_URL = "https://github.com/Bharani77/Modal.git"

# Modify the deploy_modal function to use the hardcoded URL
def deploy_modal(repo_url, modal_name="default_app"):
    # Use hardcoded repo URL instead of the one provided in the UI
    repo_url = HARDCODED_REPO_URL
    
    # Update status to "in_progress"
    deployment_status[modal_name] = {"status": "in_progress", "details": "Deployment started"}
    
    # Create a temporary directory for the operation
    temp_dir = tempfile.mkdtemp()
    original_dir = os.getcwd()
    
    try:
        # Clone the repository using hardcoded URL
        print(f"Cloning repository: {repo_url}")
        clone_process = subprocess.run(
            ["git", "clone", repo_url, temp_dir],
            capture_output=True, text=True, check=True
        )
        
        # Rest of the function remains the same
        os.chdir(temp_dir)
        env = get_modal_env(modal_name)
        
        deploy_process = subprocess.run(
            ["modal", "deploy", "modal_container.py"],
            capture_output=True, text=True,
            env=env
        )
        
        if deploy_process.returncode == 0:
            result = f"Deployment successful!\n\nOutput:\n{deploy_process.stdout}\n\nDeployed with MODAL_NAME: {modal_name}\nUsed repository: {repo_url}"
            deployment_status[modal_name] = {
                "status": "deployed",
                "details": result,
                "stdout": deploy_process.stdout,
                "deployed_at": subprocess.check_output(["date"]).decode().strip(),
                "repo_url": repo_url
            }
        else:
            result = f"Deployment failed.\n\nError:\n{deploy_process.stderr}\n\nOutput:\n{deploy_process.stdout}\n\nAttempted with MODAL_NAME: {modal_name}\nUsed repository: {repo_url}"
            deployment_status[modal_name] = {
                "status": "failed",
                "details": result,
                "stderr": deploy_process.stderr,
                "stdout": deploy_process.stdout,
                "repo_url": repo_url
            }
        return result
            
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        deployment_status[modal_name] = {"status": "error", "details": error_msg, "repo_url": repo_url}
        return error_msg
    finally:
        os.chdir(original_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)

    # Function to check Modal app status
def check_modal_status(modal_name):
    try:
        # If we have status in our dictionary
        if modal_name in deployment_status:
            return deployment_status[modal_name]
        
        # If not in our dictionary, check with modal CLI
        env = get_modal_env(modal_name)
        
        status_process = subprocess.run(
            ["modal", "app", "show", modal_name],
            capture_output=True, text=True,
            env=env
        )
        
        if status_process.returncode == 0:
            return {
                "status": "deployed",
                "details": "App is deployed",
                "cli_output": status_process.stdout
            }
        else:
            return {
                "status": "unknown",
                "details": "App not found or error checking status",
                "cli_output": status_process.stderr
            }
    except Exception as e:
        return {
            "status": "error", 
            "details": f"Error checking status: {str(e)}"
        }

# Function to undeploy Modal app
def undeploy_modal(modal_name):
    try:
        # Update status
        if modal_name in deployment_status:
            deployment_status[modal_name] = {"status": "undeploying", "details": "Undeployment in progress"}
        
        # Run modal undeploy command
        env = get_modal_env(modal_name)
        
        undeploy_process = subprocess.run(
            ["modal", "app", "stop", modal_name],
            capture_output=True, text=True,
            env=env
        )
        
        if undeploy_process.returncode == 0:
            result = f"Undeployment successful!\n\nOutput:\n{undeploy_process.stdout}\n\nUndeployed app: {modal_name}"
            deployment_status[modal_name] = {
                "status": "undeployed",
                "details": result,
                "stdout": undeploy_process.stdout,
                "undeployed_at": subprocess.check_output(["date"]).decode().strip()
            }
        else:
            result = f"Undeployment failed.\n\nError:\n{undeploy_process.stderr}\n\nOutput:\n{undeploy_process.stdout}\n\nAttempted with MODAL_NAME: {modal_name}"
            deployment_status[modal_name] = {
                "status": "undeploy_failed",
                "details": result,
                "stderr": undeploy_process.stderr
            }
        return result
        
    except Exception as e:
        error_msg = f"An error occurred during undeployment: {str(e)}"
        deployment_status[modal_name] = {"status": "error", "details": error_msg}
        return error_msg

# Add FastAPI endpoints
@app.post("/api/deploy")
async def api_deploy(request: DeployRequest):
    # Note that we're passing request.repo_url but it will be overridden inside the function
    result = deploy_modal(request.repo_url, request.modal_name)
    return {"result": result, "note": f"Using hardcoded repository: {HARDCODED_REPO_URL}"}

@app.post("/api/status")
async def api_status(request: StatusRequest):
    status = check_modal_status(request.modal_name)
    return status

@app.post("/api/undeploy")
async def api_undeploy(request: UndeployRequest):
    result = undeploy_modal(request.modal_name)
    return {"result": result}

# Handle OPTIONS requests for CORS preflight
@app.options("/{path:path}")
async def handle_options(request: Request, path: str):
    origin = request.headers.get("Origin", "")
    domain = ""
    
    # Extract domain from origin
    if origin:
        if "://" in origin:
            domain = origin.split("://")[1]
        if "/" in domain:
            domain = domain.split("/")[0]
        if ":" in domain:
            domain = domain.split(":")[0]
    
    # Create response with appropriate headers
    response = Response()
    
    # If origin is from an allowed domain, add CORS headers
    if domain in ALLOWED_DOMAINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    
    return response

# Add CORS headers to responses
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    # Process the request
    response = await call_next(request)
    
    # Get the origin from the request headers
    origin = request.headers.get("Origin", "")
    domain = ""
    
    # Extract domain from origin
    if origin:
        if "://" in origin:
            domain = origin.split("://")[1]
        if "/" in domain:
            domain = domain.split("/")[0]
        if ":" in domain:
            domain = domain.split(":")[0]
    
    # If origin is from an allowed domain, add CORS headers
    if domain in ALLOWED_DOMAINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    
    return response

# Create Gradio interface
with gr.Blocks() as demo:
    gr.Markdown("# Modal Deployment Tool")
    gr.Markdown("Enter the Git repository URL containing your modal_container.py file and the Modal application name")
    
    with gr.Row():
        repo_url = gr.Textbox(
            label="Git Repository URL", 
            placeholder="https://github.com/yourusername/yourrepo.git"
        )
    
    with gr.Row():
        modal_name = gr.Textbox(
            label="Modal Application Name",
            placeholder="my_modal_app",
            value="default_app"
        )
    
    with gr.Row():
        deploy_button = gr.Button("Deploy to Modal")
        status_button = gr.Button("Check Status")
        undeploy_button = gr.Button("Undeploy App", variant="secondary")
    
    output = gr.Textbox(label="Result", lines=10)
    
    deploy_button.click(
        fn=deploy_modal,
        inputs=[repo_url, modal_name],
        outputs=output
    )
    
    status_button.click(
        fn=lambda name: json.dumps(check_modal_status(name), indent=2),
        inputs=[modal_name],
        outputs=output
    )
    
    undeploy_button.click(
        fn=undeploy_modal,
        inputs=[modal_name],
        outputs=output
    )

# Mount the Gradio app to FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

# For direct Gradio launch (development)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
