import os
from modal import Image, App, asgi_app
import subprocess
import threading
import time

# Use an environment variable for the app name, defaulting to "galaxykick-app"
app_name = os.environ.get("MODAL_APP_NAME", "web")
# Create a Modal app with the provided app name
app = App(app_name)

# Create a Docker image directly from the Docker Hub image
image = Image.from_registry(
    "bharanidharan/galaxykick:v72",
    add_python="3.9"
).pip_install(
    "requests",
    "flask",
    "flask-cors",
    "httpx",
    "fastapi",
    "uvicorn"
)

# This function will execute the container's entrypoint/command
def run_container_entrypoint():
    print("Starting container service...")
    try:
        if os.path.exists("/galaxybackend/app.py"):
            subprocess.Popen(["python3", "/galaxybackend/app.py"])
    except Exception as e:
        print(f"Error starting container process: {e}")
    print("Container service started (or attempted to start)")

# Create a web app that serves the Docker container
@app.function(
    image=image,
    min_containers=1,
    cpu=1.5,        # 1.5 CPU cores
    memory=1500     # 1500MB RAM
)
@asgi_app()
def web_app():
    from fastapi import FastAPI, Request, HTTPException
    from fastapi.responses import StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import httpx
    
    fastapp = FastAPI()
    
    # Define allowed origins
    ALLOWED_ORIGINS = [
        "galaxykicklock.web.app",
        "lightning.ai",
        "huggingface.co",
        "buddymaster77hugs-gradiodocker.hf.space",
        "bharani77--bharanitest-web-app.modal.run",
        "modal.com"
    ]
    
    # Add CORS middleware with restricted origins
    fastapp.add_middleware(
        CORSMiddleware,
        allow_origins=[f"https://{origin}" for origin in ALLOWED_ORIGINS] + 
                     [f"http://{origin}" for origin in ALLOWED_ORIGINS],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @fastapp.on_event("startup")
    def startup_event():
        thread = threading.Thread(target=run_container_entrypoint)
        thread.daemon = True
        thread.start()
        time.sleep(10)
        print("FastAPI startup complete, container service should be running")
    
    # Helper function to check if the origin is allowed
    def is_origin_allowed(request: Request) -> bool:
        origin = request.headers.get("origin", "")
        if not origin:
            # If no origin header, check referer as fallback
            referer = request.headers.get("referer", "")
            if referer:
                for allowed in ALLOWED_ORIGINS:
                    if allowed in referer:
                        return True
            return False
        
        # Check if origin matches any allowed domain
        for allowed in ALLOWED_ORIGINS:
            if allowed in origin:
                return True
        return False
    
    @fastapp.get("/")
    async def root(request: Request):
        if not is_origin_allowed(request):
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
        return {"message": "GalaxyKick API is running. Access endpoints using the proper paths."}
    
    @fastapp.get("/{path:path}")
    async def get_route(path: str, request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        url = f"http://localhost:7860/{path}"
        params = dict(request.query_params)
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, follow_redirects=True)
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to connect to container service: {str(e)}"}
            )
    
    @fastapp.post("/{path:path}")
    async def post_route(path: str, request: Request):
        # Validate origin before processing request
        if not is_origin_allowed(request):
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
            
        url = f"http://localhost:7860/{path}"
        body = await request.body()
        headers = {key: value for key, value in request.headers.items() if key.lower() != "host"}
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url, 
                    content=body, 
                    headers=headers,
                    follow_redirects=True
                )
                return StreamingResponse(
                    content=response.aiter_bytes(),
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to connect to container service: {str(e)}"}
            )
    
    @fastapp.options("/{path:path}")
    async def options_route(path: str, request: Request):
        # Validate origin for OPTIONS requests as well
        if not is_origin_allowed(request):
            raise HTTPException(status_code=403, detail="Access denied: Origin not allowed")
        return {}
            
    return fastapp

@app.local_entrypoint()
def main():
    print(f"Starting the {app_name} app on Modal")
    print("Once deployed, access your app at the provided Modal URL")
    print("To test locally: modal serve modal_container.py")
    print("To deploy: modal deploy modal_container.py")
