import gradio as gr
import subprocess
import os
import tempfile
import shutil
import json
from fastapi import FastAPI
from pydantic import BaseModel

# Create the FastAPI app
app = FastAPI()

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

# Function to handle deployment
def deploy_modal(repo_url, modal_name="default_app"):
    # Update status to "in_progress"
    deployment_status[modal_name] = {"status": "in_progress", "details": "Deployment started"}
    
    # Create a temporary directory for the operation
    temp_dir = tempfile.mkdtemp()
    original_dir = os.getcwd()
    
    try:
        # Clone the repository
        clone_process = subprocess.run(
            ["git", "clone", repo_url, temp_dir],
            capture_output=True, text=True, check=True
        )
        
        # Change to the temp directory
        os.chdir(temp_dir)
        
        # Set environment variable for the modal_name
        env = os.environ.copy()
        env["MODAL_APP_NAME"] = modal_name
        
        # Run modal deploy command with the environment variable
        deploy_process = subprocess.run(
            ["modal", "deploy", "modal_container.py"],
            capture_output=True, text=True,
            env=env
        )
        
        # Prepare the result and update status
        if deploy_process.returncode == 0:
            result = f"Deployment successful!\n\nOutput:\n{deploy_process.stdout}\n\nDeployed with MODAL_NAME: {modal_name}"
            deployment_status[modal_name] = {
                "status": "deployed",
                "details": result,
                "stdout": deploy_process.stdout,
                "deployed_at": subprocess.check_output(["date"]).decode().strip()
            }
        else:
            result = f"Deployment failed.\n\nError:\n{deploy_process.stderr}\n\nOutput:\n{deploy_process.stdout}\n\nAttempted with MODAL_NAME: {modal_name}"
            deployment_status[modal_name] = {
                "status": "failed",
                "details": result,
                "stderr": deploy_process.stderr,
                "stdout": deploy_process.stdout
            }
        return result
            
    except Exception as e:
        error_msg = f"An error occurred: {str(e)}"
        deployment_status[modal_name] = {"status": "error", "details": error_msg}
        return error_msg
    finally:
        # Return to original directory
        os.chdir(original_dir)
        # Clean up the temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

# Function to check Modal app status
def check_modal_status(modal_name):
    try:
        # If we have status in our dictionary
        if modal_name in deployment_status:
            return deployment_status[modal_name]
        
        # If not in our dictionary, check with modal CLI
        env = os.environ.copy()
        env["MODAL_APP_NAME"] = modal_name
        
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
        env = os.environ.copy()
        env["MODAL_APP_NAME"] = modal_name
        
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
    result = deploy_modal(request.repo_url, request.modal_name)
    return {"result": result}

@app.post("/api/status")
async def api_status(request: StatusRequest):
    status = check_modal_status(request.modal_name)
    return status

@app.post("/api/undeploy")
async def api_undeploy(request: UndeployRequest):
    result = undeploy_modal(request.modal_name)
    return {"result": result}

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
