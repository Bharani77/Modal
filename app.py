import gradio as gr
import subprocess
import os
import tempfile
import shutil
from fastapi import FastAPI
from pydantic import BaseModel

# Create the FastAPI app
app = FastAPI()

# Create a data model for the request
class DeployRequest(BaseModel):
    repo_url: str
    modal_name: str = "default_app"  # Default value if not provided

# Function to handle deployment
def deploy_modal(repo_url, modal_name="default_app"):
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
        
        # Prepare the result
        if deploy_process.returncode == 0:
            return f"Deployment successful!\n\nOutput:\n{deploy_process.stdout}\n\nDeployed with MODAL_NAME: {modal_name}"
        else:
            return f"Deployment failed.\n\nError:\n{deploy_process.stderr}\n\nOutput:\n{deploy_process.stdout}\n\nAttempted with MODAL_NAME: {modal_name}"
            
    except Exception as e:
        return f"An error occurred: {str(e)}"
    finally:
        # Return to original directory
        os.chdir(original_dir)
        # Clean up the temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

# Add a FastAPI endpoint that correctly accepts JSON
@app.post("/api/deploy")
async def api_deploy(request: DeployRequest):
    result = deploy_modal(request.repo_url, request.modal_name)
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
    
    output = gr.Textbox(label="Deployment Result", lines=10)
    
    deploy_button.click(
        fn=deploy_modal,
        inputs=[repo_url, modal_name],
        outputs=output
    )

# Mount the Gradio app to FastAPI
app = gr.mount_gradio_app(app, demo, path="/")

# For direct Gradio launch (development)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7860)
