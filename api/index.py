# api/index.py
import gradio as gr
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

def greet(name):
    return f"Hello {name}!"

gradio_app = gr.Interface(fn=greet, inputs="text", outputs="text")

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def main():
    return gradio_app.launch(share=False, inline=True, prevent_thread_lock=True)
