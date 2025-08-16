from fastapi import FastAPI
from pydantic import BaseModel
from app.roadmap import generate_roadmap
from app.visualize import generate_image_base64

app = FastAPI()


class PromptRequest(BaseModel):
    prompt: str


@app.post("/roadmap")
async def roadmap(req: PromptRequest):
    roadmap_json = await generate_roadmap(req.prompt)

    image_base64 = None
    try:
        image_base64 = generate_image_base64(roadmap_json)
    except Exception as e:
        print(f"⚠️ Image generation failed: {e}")
        image_base64 = None

    return {"roadmap": roadmap_json, "image": image_base64}
