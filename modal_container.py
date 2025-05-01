import os
from modal import Image, App, asgi_app
import subprocess
import threading
import time
import socket
from urllib.parse import urlparse

# Use an environment variable for the app name, defaulting to "web"
app_name = os.environ.get("MODAL_APP_NAME", "web")
# Create a Modal app with the provided app name
app = App(app_name)

# Create a Docker image directly from the Docker Hub image
image = Image.from_registry(
    "bharanidharan/galaxykick:v91",
    add_python="3.9"
).pip_install(
    "requests",
    "flask",
    "flask-cors",
    "httpx",
    "fastapi",
    "uvicorn"
)

# Function to check if a port is open
def is_port_open(port, host='localhost', timeout=1):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0

# This function will execute the container's entrypoint/command and keep it running
def run_container_entrypoint():
    while True:
        print("Starting container service...")
        try:
            if os.path.exists("/galaxybackend/app.py"):
                process = subprocess.Popen(["python3", "/galaxybackend/app.py"])
                process.wait()
                print("Container service process exited with code", process.returncode)
            else:
                print("Warning: /galaxybackend/app.py not found")
                break
        except Exception as e:
            print(f"Error starting container process: {e}")
        time.sleep(5)  # Wait 5 seconds before restarting

# Create a web app that serves the Docker container
@app.function(
    image=image,
    min_containers=1,
    max_containers=1,  # Added to prevent autoscaling
    cpu=1.5,
    memory=2048
)
@asgi_app()
def web_app():
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import httpx
    import logging
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("galaxykick-api")
    
    fastapp = FastAPI()
    
    # Define allowed origins - exact domains that are allowed
    ALLOWED_ORIGINS = [
        "galaxykicklock.web.app",
        "lightning.ai",
        "huggingface.co",
        "buddymaster77hugs-gradiodocker.hf.space",
        "bharani77--bharanitest-web-app.modal.run",
        "modal.com"
    ]
    
    # Convert to a set for faster lookups
    ALLOWED_ORIGINS_SET = set(ALLOWED_ORIGINS)
    
    # Add full URLs to CORS middleware (both http and https)
    CORS_ALLOWED_ORIGINS = []
    for origin in ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(f"https://{origin}")
        CORS_ALLOWED_ORIGINS.append(f"http://{origin}")
        # Also include subdomains
        if "." in origin:
            CORS_ALLOWED_ORIGINS.append(f"https://*.{origin}")
            CORS_ALLOWED_ORIGINS.append(f"http://*.{origin}")
    
    # Add CORS middleware with restricted origins
    fastapp.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Global variable to track container service status
    container_service_ready = False
    
    @fastapp.on_event("startup")
    def startup_event():
        global container_service_ready
        
        # Start the container service in a background thread
        thread = threading.Thread(target=run_container_entrypoint)
        thread.daemon = True
        thread.start()
        
        # Wait for container service to be ready with a timeout
        max_wait_time = 60  # Maximum wait time in seconds
        wait_interval = 2   # Check every 2 seconds
        total_waited = 0
        
        logger.info("Waiting for container service to start...")
        while total_waited < max_wait_time:
            if is_port_open(7860):
                container_service_ready = True
                logger.info(f"Container service is ready after {total_waited} seconds")
                break
            time.sleep(wait_interval)
            total_waited += wait_interval
            logger.info(f"Waiting for container service... ({total_waited}/{max_wait_time}s)")
        
        if not container_service_ready:
            logger.warning("Container service not detected after timeout, proceeding anyway")
    
    # Helper function to extract domain from URL
    def extract_domain(url):
        if not url:
            return None
        
        # Add scheme if not present
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            
            # Remove port if present
            if ':' in domain:
                domain = domain.split(':')[0]
                
            # Remove 'www.' prefix if present
            if domain.startswith('www.'):
                domain = domain[4:]
                
            return domain
        except:
            return None
    
    # Helper function to check if the domain is in allowed list
    def is_domain_allowed(domain):
        if not domain:
            return False
            
        # Check exact match
        if domain in ALLOWED_ORIGINS_SET:
            return True
            
        # Check for subdomain
        for allowed in ALLOWED_ORIGINS_SET:
            if domain.endswith('.' + allowed):
                return True
                
        return False
    
    # Helper function to check if the origin is allowed
    def is_origin_allowed(request: Request) -> bool:
        # Extract and check Origin header
        origin = request.headers.get("origin")
        origin_domain = extract_domain(origin)
        if origin_domain and is_domain_allowed(origin_domain):
            logger.info(f"Access allowed for origin: {origin}")
            return True
            
        # If no origin, check Referer as fallback
        referer = request.headers.get("referer")
        referer_domain = extract_domain(referer)
        if referer_domain and is_domain_allowed(referer_domain):
            logger.info(f"Access allowed for referer: {referer}")
            return True
            
        # No valid origin or referer with allowed domain found
        logger.warning(f"Access denied. Origin: {origin}, Referer: {referer}")
        return False
    
    @fastapp.get("/")
    async def root(request: Request):
        if not is_origin_allowed(request):
            logger.warning(f"Access denied from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
        return {"message": "GalaxyKick API is running. Access endpoints using the proper paths."}
    
    @fastapp.get("/status")
    async def status(request: Request):
        # Even status endpoint should be restricted
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for status check from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        is_ready = is_port_open(7860)
        return {
            "api_status": "running",
            "container_service": "running" if is_ready else "not ready",
            "container_port_open": is_ready
        }
    
    @fastapp.get("/{path:path}")
    async def get_route(path: str, request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for GET /{path} from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        url = f"http://localhost:7860/{path}"
        params = dict(request.query_params)
        
        # Check if container service is available
        if not is_port_open(7860):
            logger.error(f"Container service not available on port 7860 for GET /{path}")
            return JSONResponse(
                status_code=503,
                content={"error": "Container service is not available or still starting"}
            )
            
        try:
            logger.info(f"Forwarding GET request to {url}")
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, params=params, follow_redirects=True)
                logger.info(f"Received response from container: {response.status_code}")
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except httpx.ConnectError as e:
            logger.error(f"Connection error to container service: {e}")
            return JSONResponse(
                status_code=503,
                content={"error": "Cannot connect to container service. It may be starting up or unavailable."}
            )
        except httpx.ReadTimeout as e:
            logger.error(f"Timeout connecting to container service: {e}")
            return JSONResponse(
                status_code=504,
                content={"error": "Connection to container service timed out"}
            )
        except Exception as e:
            logger.error(f"Error forwarding GET request to {url}: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to process request: {str(e)}"}
            )
    
    @fastapp.post("/{path:path}")
    async def post_route(path: str, request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for POST /{path} from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        url = f"http://localhost:7860/{path}"
        
        # Check if container service is available
        if not is_port_open(7860):
            logger.error(f"Container service not available on port 7860 for POST /{path}")
            return JSONResponse(
                status_code=503,
                content={"error": "Container service is not available or still starting"}
            )
        
        try:
            body = await request.body()
            headers = {key: value for key, value in request.headers.items() if key.lower() != "host"}
            
            logger.info(f"Forwarding POST request to {url}")
            async with httpx.AsyncClient(timeout=60.0) as client:  # Increased timeout for POST requests
                response = await client.post(
                    url, 
                    content=body, 
                    headers=headers,
                    follow_redirects=True
                )
                logger.info(f"Received response from container: {response.status_code}")
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except httpx.ConnectError as e:
            logger.error(f"Connection error to container service: {e}")
            return JSONResponse(
                status_code=503,
                content={"error": "Cannot connect to container service. It may be starting up or unavailable."}
            )
        except httpx.ReadTimeout as e:
            logger.error(f"Timeout connecting to container service: {e}")
            return JSONResponse(
                status_code=504,
                content={"error": "Connection to container service timed out"}
            )
        except Exception as e:
            logger.error(f"Error forwarding POST request to {url}: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to process request: {str(e)}"}
            )
    
    @fastapp.options("/{path:path}")
    async def options_route(path: str, request: Request):
        # Validate origin for OPTIONS requests as well
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for OPTIONS /{path} from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
        return {}
            
    return fastapp

@app.local_entrypoint()
def main():
    print(f"Starting the {app_name} app on Modal")
    print("Once deployed, access your app at the provided Modal URL")
    print("To test locally: modal serve modal_container.py")
    print("To deploy: modal deploy modal_container.py")
