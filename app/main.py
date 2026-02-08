from fastapi import FastAPI, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Response, Request, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict
from app.services import (
    chat_with_agent, analyze_image, get_dashboard_update, stats_manager, get_companies,
    register_company, get_company_by_tagline, login_admin, get_pending_claims, 
    update_claim_status, refine_policy_with_gemini
)
import shutil
import os
import json

app = FastAPI(title="Support Assistance Portal")

# CORS Setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- WebSocket Manager ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# Models
class ChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = []
    company_policy: Optional[str] = "Standard Policy"
    customer_id: Optional[str] = None
    image_analysis: Optional[str] = None
    evidence_image_url: Optional[str] = None # URL of uploaded image
    company_id: Optional[str] = None # Added for multi-tenant context

class ChatResponse(BaseModel):
    reply: str
    action: Optional[dict] = None

class RegisterRequest(BaseModel):
    name: str
    description: str
    tagline: str
    banner_color: str
    policy: str

class AdminLoginRequest(BaseModel):
    tagline: str
    username: str
    password: str

class DecisionRequest(BaseModel):
    claim_id: str
    claim_type: str # 'refund' or 'escalation'
    decision: str # 'APPROVED' or 'DECLINED'
    correction: Optional[str] = None
    company_id: str
    issue_context: Optional[str] = None # For Gemini learning

# API Endpoints
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "Assistance Portal (Gemini)"}

@app.get("/api/companies")
async def get_companies_endpoint():
    return get_companies()

@app.post("/api/register")
async def register_company_endpoint(req: RegisterRequest):
    result = register_company(
        req.name, req.description, req.tagline, req.banner_color, req.policy
    )
    if not result:
        raise HTTPException(status_code=500, detail="Registration failed")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/api/company/{tagline}")
async def get_company_details(tagline: str):
    data = get_company_by_tagline(tagline)
    if not data:
        raise HTTPException(status_code=404, detail="Company not found")
    return data

@app.post("/api/admin/login")
async def admin_login(req: AdminLoginRequest, response: Response):
    user = login_admin(req.tagline, req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Set cookie for server-side validation
    response.set_cookie(
        key="admin_tagline", 
        value=user['tagline'], 
        httponly=True, 
        max_age=86400,
        samesite="lax"
    )

    return {
        "status": "success",
        "company_id": user['id'],
        "company_name": user['name'],
        "banner_color": user.get('banner_color'),
        "return_policy": user.get('return_policy') 
    }

@app.post("/api/admin/logout")
async def admin_logout(response: Response):
    response.delete_cookie("admin_tagline")
    return {"status": "success"}

@app.get("/api/admin/claims")
async def get_claims(company_id: str):
    return get_pending_claims(company_id)

@app.post("/api/admin/claims/decide")
async def decide_claim(req: DecisionRequest):
    # 1. Update Status
    table = "refund_requests"
    if req.claim_type == 'escalation':
        table = "escalation_requests"
    elif req.claim_type == 'payout':
        table = "company_refund_queue"
        
    status = req.decision # Use exact decision if passed (e.g. PAID), or map
    if req.decision == "APPROVED": status = "APPROVED" # Default mapping
    elif req.decision == "DECLINED": status = "REJECTED"
    
    # Clear context if final decision made using "delete chat context" rule
    update_claim_status(table, req.claim_id, status, clear_context=True)
    
    # 2. Feedback Loop
    is_policy_trigger = (req.decision == "DECLINED" and req.correction and 
                        (req.claim_type == 'refund' or req.claim_type == 'payout'))
                        
    if is_policy_trigger:
         # Fetch company policy
         all_companies = get_companies()
         current_policy = "Standard Policy"
         for c in all_companies:
             if c['id'] == req.company_id:
                 current_policy = c['return_policy']
                 break
         
         # Refine Policy
         new_policy = await refine_policy_with_gemini(req.company_id, req.issue_context, req.correction, current_policy)
         return {"status": "updated", "new_policy": new_policy}

    return {"status": "success"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text() # Keep connection alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    raw_reply = await chat_with_agent(
        req.message, req.history, 
        image_analysis=req.image_analysis, 
        company_policy=req.company_policy, 
        customer_id=req.customer_id,
        evidence_image_url=req.evidence_image_url,
        company_id=req.company_id
    )
    
    # Extract JSON action if present
    reply_text = raw_reply
    action_data = None
    
    if "```json" in raw_reply:
        try:
            json_str = raw_reply.split("```json")[1].split("```")[0]
            action_data = json.loads(json_str)
            reply_text = raw_reply.split("```json")[0].strip()
        except:
            pass

    # Broadcast Dashboard Updates
    events = get_dashboard_update(action_json=action_data)
    for event in events:
        await manager.broadcast(event)
        
    # Broadcast Stats Update
    await manager.broadcast({
        "type": "stats",
        "data": stats_manager.get_stats()
    })

    return {"reply": reply_text, "action": action_data}

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...), message: str = Form(...), company_policy: str = Form("Standard Policy")):
    """
    Handle image upload and immediate analysis/chat
    """
    # Save temp file
    temp_dir = "/tmp/uploads"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = f"{temp_dir}/{file.filename}"
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Analyze (Gemini Vision)
    analysis_result = analyze_image(file_path)
    
    # Logic Gate: Check for Rejection
    is_rejected = "Verification Failed" in analysis_result
    
    if is_rejected:
         await manager.broadcast({
            "type": "event",
            "icon": "block",
            "title": "Image Rejected",
            "time": "Now",
            "subtitle": "Fake/Digital image detected"
        })
         # STOP HERE - Return rejection without chatting
         return {
             "reply": "Verification Failed: The image appears to be digital or AI-generated. Please upload a real photo taken with a camera.",
             "analysis": analysis_result,
             "filename": file.filename
         }

    # If passed verification:
    await manager.broadcast({
        "type": "event",
        "icon": "image",
        "title": "Image Analyzed",
        "time": "Now",
        "subtitle": "Gemini has processed the image"
    })
    
    # Construct accessible URL
    file_url = f"/uploads/{file.filename}"
    
    # Get Chat Response with Context
    raw_reply = await chat_with_agent(
        message, 
        image_analysis=analysis_result, 
        company_policy=company_policy,
        evidence_image_url=file_url
    )
    
    # Parse Action
    reply_text = raw_reply
    action_data = None
    if "```json" in raw_reply:
        try:
            json_str = raw_reply.split("```json")[1].split("```")[0]
            action_data = json.loads(json_str)
            reply_text = raw_reply.split("```json")[0].strip()
        except:
            pass
            
    # Broadcast Policy Events if action taken
    if action_data:
        events = get_dashboard_update(action_json=action_data)
        for event in events:
            if event["icon"] != "image" and event["icon"] != "block": 
                await manager.broadcast(event)
                
    # Broadcast Stats Update
    await manager.broadcast({
        "type": "stats",
        "data": stats_manager.get_stats()
    })
    
    return {
        "reply": reply_text,
        "analysis": analysis_result,
        "filename": file.filename
    }

# Use /tmp for Vercel
upload_dir = "/tmp/uploads"
os.makedirs(upload_dir, exist_ok=True)

# Mount Static Files (Frontend)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# Mount Flutter App Static Directories
app.mount("/assets", StaticFiles(directory="assistance_web/assets"), name="flutter_assets")
app.mount("/canvaskit", StaticFiles(directory="assistance_web/canvaskit"), name="flutter_canvaskit")
app.mount("/icons", StaticFiles(directory="assistance_web/icons"), name="flutter_icons")


@app.get("/{tagline}/admin")
async def company_admin(tagline: str, request: Request):
    # 1. Check if company exists
    company = get_company_by_tagline(tagline)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # 2. Check Auth (Cookie)
    # If cookie is present BUT belongs to another company -> 401
    # If cookie is missing -> Allow (Client will show login form)
    cookie_tagline = request.cookies.get("admin_tagline")
    
    if cookie_tagline and cookie_tagline != tagline:
        # User is logged in as someone else
        raise HTTPException(status_code=401, detail="You are logged in to another company. Please logout first.")
        
    return FileResponse("app/static/admin.html")

@app.get("/")
async def root():
    return FileResponse("assistance_web/index.html")

@app.get("/{path_name}")
async def dynamic_route(path_name: str):
    # 1. Check for Flutter web root files (e.g. flutter.js, manifest.json)
    # Security: Ensure path_name doesn't contain traversal characters (basic check)
    if ".." in path_name or "/" in path_name:
         # Fallback to company handling or 404
         pass
    else:
        potential_file = os.path.join("assistance_web", path_name)
        if os.path.isfile(potential_file):
            return FileResponse(potential_file)

    # 2. Otherwise assume it is a company tagline
    if get_company_by_tagline(path_name):
        return FileResponse("app/static/index.html")
    
    # 3. If neither, it's a 404
    raise HTTPException(status_code=404, detail="Not Found")
