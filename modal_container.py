import os
from modal import Image, App, asgi_app
import subprocess
import threading
import time
import socket
import json
from urllib.parse import urlparse

# Use an environment variable for the app name, defaulting to "web"
app_name = os.environ.get("MODAL_APP_NAME", "raja")
# Create a Modal app with the provided app name
app = App(app_name)

# Create a Docker image directly from the Docker Hub image
image = Image.from_registry(
    "bharanidharan/galaxykick:v100",
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

# Global variable to store variables passed from the app
app_variables = {}

# Function to start the container and keep it running in the background
def run_container_background():
    # Ensure PM2 is installed and available
    try:
        subprocess.run(["pm2", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("PM2 not found, installing...")
        subprocess.run(["npm", "install", "-g", "pm2"], check=True)
    
    print("Container is running in background mode")
    
    # Keep the thread alive
    while True:
        time.sleep(10)  # Just keep the thread alive

# Function to start galaxy_1.js with PM2 and provided variables
def start_galaxy_with_variables(variables):
    print(f"Starting galaxy_1.js with variables: {variables}")
    
    # Convert variables to environment variables for PM2
    env_vars = " ".join([f"{k}={v}" for k, v in variables.items()])
    
    try:
        # Stop any existing process first
        subprocess.run("pm2 stop galaxy_1 || true", shell=True)
        subprocess.run("pm2 delete galaxy_1 || true", shell=True)
        
        # Start with the new variables
        cmd = f"pm2 start galaxy_1.js --name galaxy_1 --update-env -- {env_vars}"
        print(f"Executing command: {cmd}")
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        print(f"PM2 start result: {result.stdout}")
        
        if result.returncode != 0:
            print(f"Error running PM2: {result.stderr}")
            return {"success": False, "error": result.stderr}
            
        return {"success": True, "message": "Galaxy application started successfully"}
    except Exception as e:
        print(f"Exception while starting galaxy_1.js: {str(e)}")
        return {"success": False, "error": str(e)}

# Create a web app that serves the Docker container
@app.function(
    image=image,
    min_containers=1,
    max_containers=1,  # Added to prevent autoscaling
    cpu=4,
    memory=4500
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
        "bharani77--raja-web-app.modal.run",
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
    
    # Global variable to track container background service status
    container_background_ready = False
    
    @fastapp.on_event("startup")
    def startup_event():
        global container_background_ready
        
        # Start the container in background mode
        logger.info("Starting container in background mode...")
        thread = threading.Thread(target=run_container_background)
        thread.daemon = True
        thread.start()
        
        # Mark container as ready
        container_background_ready = True
        logger.info("Container background service started")
    
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
            
        # Check PM2 status
        try:
            pm2_result = subprocess.run("pm2 list --format json", shell=True, capture_output=True, text=True)
            pm2_status = "running" if pm2_result.returncode == 0 else "not running"
            
            # Try to parse PM2 json output
            try:
                pm2_processes = json.loads(pm2_result.stdout)
                galaxy_process = next((p for p in pm2_processes if p.get("name") == "galaxy_1"), None)
                galaxy_status = galaxy_process.get("pm2_env", {}).get("status", "unknown") if galaxy_process else "not found"
            except:
                galaxy_status = "unknown"
                
        except Exception as e:
            pm2_status = f"error: {str(e)}"
            galaxy_status = "unknown"
            
        return {
            "api_status": "running",
            "container_background": "running" if container_background_ready else "not ready",
            "pm2_status": pm2_status,
            "galaxy_app_status": galaxy_status
        }
    
    # New endpoint to start galaxy_1.js with provided variables
    @fastapp.post("/start")
    async def start_galaxy_app(request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for /start from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
        
        # Check if container is ready
        if not container_background_ready:
            logger.error("Container background service not ready")
            return JSONResponse(
                status_code=503,
                content={"success": False, "error": "Container background service is not ready"}
            )
            
        try:
            # Get variables from request body
            variables = await request.json()
            logger.info(f"Received start request with variables: {variables}")
            
            # Start galaxy_1.js with PM2 and the provided variables
            result = start_galaxy_with_variables(variables)
            
            if result["success"]:
                return JSONResponse(
                    status_code=200,
                    content={"success": True, "message": result["message"]}
                )
            else:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": result["error"]}
                )
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON in request body")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": "Invalid JSON in request body"}
            )
        except Exception as e:
            logger.error(f"Error processing start request: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": f"Failed to process request: {str(e)}"}
            )
    
    @fastapp.get("/{path:path}")
    async def get_route(path: str, request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            logger.warning(f"Access denied for GET /{path} from origin: {request.headers.get('origin', 'Unknown')}")
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        url = f"http://localhost:7860/{path}"
        params = dict(request.query_params)
        
        # Check if port 7860 is open
        if not is_port_open(7860):
            logger.warning(f"Port 7860 not open for GET /{path}")
            # Instead of returning an error, we could check if the galaxy app is running through PM2
            try:
                pm2_result = subprocess.run("pm2 list | grep galaxy_1", shell=True, capture_output=True)
                if pm2_result.returncode == 0:
                    logger.info("Galaxy app is running through PM2 but port 7860 is not open")
                else:
                    logger.warning("Galaxy app is not running through PM2")
            except Exception as e:
                logger.error(f"Error checking PM2 status: {str(e)}")
            
            return JSONResponse(
                status_code=503,
                content={"error": "Container service is not available on port 7860"}
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
        
        # Check if port 7860 is open
        if not is_port_open(7860):
            logger.warning(f"Port 7860 not open for POST /{path}")
            return JSONResponse(
                status_code=503,
                content={"error": "Container service is not available on port 7860"}
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
