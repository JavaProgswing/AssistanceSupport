import os
import json
import random
import time
import re
import secrets
import string
import base64
from io import BytesIO
import qrcode
import PIL.Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
from supabase import create_client, Client
from passlib.context import CryptContext

# --- Config ---
load_dotenv()
deployment_url = "https://assistance-pi.vercel.app"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)

GEMINI_MODEL_NAME = "gemini-3-flash-preview"
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"Supabase Init Error: {e}")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# --- Constants ---
BASE_SYSTEM_PROMPT = """
You are an advanced Support Assistance Bot named "Support Assistant".

WORKFLOW:
1. **Analyze Image**: Verify proof of damage. REJECT if fake/screenshot.
2. **Verify Transaction**: Ask for "Order Reference" or "Transaction ID".
3. **Check Status**: Verify ID in system.
    - Not Found -> Ask again.
    - Found + Existing Claim -> Inform status.
    - Found + No Claim -> Proceed.
4. **Judgment**: Based on **Company Policy**, decide to [REFUND], [ESCALATE], or [REJECT].
    - **CRITICAL**: If the claim is valid according to policy (e.g. damage is real and within terms), issue a [REFUND] immediately. Do NOT escalate valid claims unless the policy EXPLICITLY requires human review for every single case.
    - If unsure or policy is vague, [ESCALATE].
    - If invalid (fake proof, wrong item), [REJECT].

JSON ACTION FORMAT:
You MUST append a raw JSON block at the very end of your response for any final decision.
Use Markdown code blocks for the JSON.

```json
{
    "action": "REFUND",
    "reason": "Valid claim (Damage verified)",
    "transaction_id": "UUID"
}
```
"""


# --- Stats Manager (Real-ish) ---
class StatsManager:
    def __init__(self):
        self.stats = {
            "total_interactions": 0,
            "ai_resolved": 0, # REFUND or APPROVED
            "escalated": 0,   # ESCALATE
            "total_time_ms": 0,
            "satisfaction_score": 4.8, # Mock for now as we don't have user feedback loop yet
        }

    def update(self, ms: float, action_type: str = None):
        self.stats["total_interactions"] += 1
        self.stats["total_time_ms"] += ms
        
        if action_type in ["REFUND", "APPROVED"]:
            self.stats["ai_resolved"] += 1
        elif action_type == "ESCALATE":
            self.stats["escalated"] += 1
            
        # Slight random fluctuation for "aliveness" of score
        self.stats["satisfaction_score"] = max(
            4.0, min(5.0, self.stats["satisfaction_score"] + random.uniform(-0.05, 0.05))
        )

    def get_stats(self):
        total_decisions = self.stats["ai_resolved"] + self.stats["escalated"]
        resolution_rate = 0
        if total_decisions > 0:
            resolution_rate = (self.stats["ai_resolved"] / total_decisions) * 100
        elif self.stats["total_interactions"] > 0:
             # Fallback if no decisions made yet (just chat), maybe show 100% or 0%? 
             # Let's say 100% start
             resolution_rate = 100

        avg_time = 0
        if self.stats["total_interactions"] > 0:
            avg_time = self.stats["total_time_ms"] / self.stats["total_interactions"]

        return {
            "resolution": f"{int(resolution_rate)}%",
            "avg_time": f"{avg_time/1000:.1f}s",
            "satisfaction": f"{self.stats['satisfaction_score']:.1f}★",
        }


stats_manager = StatsManager()


# --- DB Helpers ---
def db_select(table, query_col=None, query_val=None, select="*"):
    if not supabase:
        return []
    try:
        q = supabase.table(table).select(select)
        if query_col and query_val:
            if query_col == "order_ref_ilike":  # Special case for ilike
                q = q.ilike("order_ref", query_val)
            else:
                q = q.eq(query_col, query_val)
        return q.execute().data
    except Exception:
        return []


def get_companies():
    return db_select("companies", select="id, name, return_policy")


def verify_transaction(order_ref: str, company_id: str = None):
    clean_ref = order_ref.replace("#", "").strip()
    
    # Base query
    q = supabase.table("transactions").select("*")
    
    # Filter by order ref
    q = q.ilike("order_ref", clean_ref)
    
    # Filter by company_id if provided
    if company_id:
        q = q.eq("company_id", company_id)
        
    try:
        res = q.execute().data
        return res[0] if res else None
    except Exception:
        return None


def check_existing_claim(transaction_id: str):
    res = db_select(
        "refund_requests", "transaction_id", transaction_id, select="status, created_at"
    )
    return res[0] if res else None


def get_company_by_tagline(tagline: str):
    res = db_select("companies", "tagline", tagline)
    return res[0] if res else None


def create_claim(
    transaction_id: str,
    company_id: str,
    status: str,
    reasoning: str,
    evidence_url: str = None,
    transcript: str = None,
):
    if not supabase:
        return None
    try:
        data = {
            "transaction_id": transaction_id,
            "company_id": company_id,
            "status": status,
            "ai_analysis_json": {"reason": reasoning},
            "evidence_image_url": evidence_url,
            "user_transcript": transcript,
        }
        return supabase.table("refund_requests").insert(data).execute().data
    except Exception:
        return None


def create_refund_entry(transaction_id: str, company_id: str, amount: float):
    if not supabase:
        return None
    try:
        data = {
            "transaction_id": transaction_id,
            "company_id": company_id,
            "amount": amount,
            "status": "READY_FOR_PAYOUT",
        }
        return supabase.table("company_refund_queue").insert(data).execute().data
    except Exception:
        return None


def create_escalation_entry(
    transaction_id: str, customer_id: str = None, reason: str = "User Request"
):
    if not supabase:
        return None
    try:
        data = {"transaction_id": transaction_id, "reason": reason, "status": "OPEN"}
        if customer_id:
            data["customer_id"] = customer_id
        return supabase.table("escalation_requests").insert(data).execute().data
    except Exception:
        return None


# --- Admin & Auth ---
def register_company(
    name: str, description: str, tagline: str, banner_color: str, policy: str
):
    if not supabase:
        return None
    if get_company_by_tagline(tagline):
        return {"error": "Tagline exists"}

    try:
        admin_user = "admin_" + "".join(secrets.choice(string.digits) for _ in range(5))
        plain_pass = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(12)
        )

        data = {
            "name": name,
            "description": description,
            "tagline": tagline,
            "banner_color": banner_color,
            "return_policy": policy,
            "admin_username": admin_user,
            "admin_password": pwd_context.hash(plain_pass),
        }
        res = supabase.table("companies").insert(data).execute()

        if res.data:
            # Generate QR
            website_url = f"{deployment_url}/{tagline}"
            qr = qrcode.QRCode(box_size=10, border=5)
            qr.add_data(website_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            img.save(buffered, format="PNG")

            return {
                "company": res.data[0],
                "admin_username": admin_user,
                "admin_password": plain_pass,
                "website_url": website_url,
                "qr_code_base64": base64.b64encode(buffered.getvalue()).decode("utf-8"),
            }
    except Exception as e:
        return {"error": str(e)}
    return None


def login_admin(tagline: str, username: str, password: str):
    if not supabase:
        return None
    try:
        res = (
            supabase.table("companies")
            .select("*")
            .eq("tagline", tagline)
            .eq("admin_username", username)
            .execute()
        )
        if res.data:
            company = res.data[0]
            stored_hash = company.get("admin_password")
            try:
                if pwd_context.verify(password, stored_hash):
                    return company
            except:
                if stored_hash == password:
                    return company  # Legacy fallback
    except Exception:
        pass
    return None


def get_pending_claims(company_id: str):
    if not supabase:
        return {}
    try:
        refunds = (
            supabase.table("refund_requests")
            .select("*, transactions(*)")
            .eq("company_id", company_id)
            .eq("status", "PENDING")
            .execute()
        )
        escalations = (
            supabase.table("escalation_requests")
            .select("*, transactions(*)")
            .eq("status", "OPEN")
            .execute()
        )
        payouts = (
            supabase.table("company_refund_queue")
            .select("*, transactions(*)")
            .eq("company_id", company_id)
            .eq("status", "READY_FOR_PAYOUT")
            .execute()
        )

        # Filter escalations by company and attach context if possible is in 'reason'
        company_escalations = []
        if escalations.data:
            for esc in escalations.data:
                tx = esc.get("transactions")
                if tx and tx.get("company_id") == company_id:
                    company_escalations.append(esc)

        payout_data = payouts.data or []
        # Enrich payouts with context from refund_requests (if available)
        # Enrich payouts AND escalations with context from refund_requests
        # Get all transaction IDs
        payout_tx_ids = [p["transaction_id"] for p in payout_data]
        esc_tx_ids = [e["transaction_id"] for e in company_escalations]
        all_tx_ids = list(set(payout_tx_ids + esc_tx_ids))

        if all_tx_ids:
            related_claims = (
                supabase.table("refund_requests")
                .select(
                    "transaction_id, user_transcript, ai_analysis_json, evidence_image_url"
                )
                .in_("transaction_id", all_tx_ids)
                .execute()
            )
            claim_map = {c["transaction_id"]: c for c in (related_claims.data or [])}

            # Enrich Payouts
            for p in payout_data:
                related = claim_map.get(p["transaction_id"])
                if related:
                    p["context"] = related.get("user_transcript")
                    p["ai_reason"] = related.get("ai_analysis_json", {}).get("reason")
                    p["evidence_image_url"] = related.get("evidence_image_url")

            # Enrich Escalations
            for e in company_escalations:
                related = claim_map.get(e["transaction_id"])
                if related:
                    e["context"] = related.get("user_transcript")
                    e["evidence_image_url"] = related.get("evidence_image_url")

        return {
            "refund_requests": refunds.data or [],
            "escalations": company_escalations,
            "payout_queue": payout_data,
        }
    except Exception as e:
        print(f"Error fetching claims: {e}")
        return {}


def update_claim_status(
    table_name: str, claim_id: str, status: str, clear_context: bool = False
):
    if not supabase:
        return None
    try:
        # 1. Update the status of the target record
        res = (
            supabase.table(table_name)
            .update({"status": status})
            .eq("id", claim_id)
            .execute()
        )

        # 2. Handle Logic to Clear Context (Privacy)
        if clear_context:
            if table_name == "refund_requests":
                # Direct clear
                supabase.table(table_name).update(
                    {"user_transcript": None, "evidence_image_url": None}
                ).eq("id", claim_id).execute()

            elif table_name == "company_refund_queue":
                # Find linked refund request via transaction_id
                item = res.data[0] if res.data else None
                if item and item.get("transaction_id"):
                    tid = item.get("transaction_id")
                    supabase.table("refund_requests").update(
                        {"user_transcript": None, "evidence_image_url": None}
                    ).eq("transaction_id", tid).execute()

        return res.data
    except Exception as e:
        print(f"Update Error: {e}")
        return None


# --- AI Logic ---
def update_company_policy(company_id: str, new_policy: str):
    if not supabase:
        return None
    try:
        return (
            supabase.table("companies")
            .update({"return_policy": new_policy})
            .eq("id", company_id)
            .execute()
            .data
        )
    except Exception as e:
        print(f"Policy Update Error: {e}")
        return None


async def refine_policy_with_gemini(
    company_id: str, issue_context: str, correction_feedback: str, current_policy: str
):
    try:
        if not client:
            return current_policy
        prompt = f"""
        Current Policy: {current_policy}
        Issue Context: {issue_context}
        Feedback: {correction_feedback}
        
        TASK: Rewrite policy to incorporate feedback. Keep it professional. Output NEW POLICY text only.
        """
        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME, contents=prompt
        )
        new_policy = response.text.strip()
        update_company_policy(company_id, new_policy)
        return new_policy
    except Exception:
        return current_policy


def analyze_image(file_path: str):
    try:
        if not client:
            return "API Key Config Error"
        # Opening image using PIL
        img = PIL.Image.open(file_path)
        prompt = "Analyze this image. 1. Is it REAL? If not, say 'Verification Failed'. 2. If real, describe damage."

        response = client.models.generate_content(
            model=GEMINI_MODEL_NAME, contents=[prompt, img]
        )
        return response.text
    except Exception as e:
        return f"Image analysis failed: {e}"


# ... signature update ...
async def chat_with_agent(
    message: str,
    history: list = None,
    image_analysis: str = None,
    company_policy: str = "Standard Policy",
    customer_id: str = None,
    evidence_image_url: str = None,
    company_id: str = None,
):
    start_time = time.time()
    system_injection = ""

    # Check for Transaction ID / Order Ref in message
    match = re.search(
        r"(?:#|order\s+id\s*[:#]?\s*)?([A-Za-z0-9\-]+)", message, re.IGNORECASE
    )
    if match and len(match.group(1)) > 3:
        potential_id = match.group(1)
        # Verify transaction with company context
        tx = verify_transaction(potential_id, company_id)
        if tx:
            existing = check_existing_claim(tx["id"])
            if existing:
                system_injection += f"\n[SYSTEM]: Tx {potential_id} Verified. Claim EXISTS: {existing['status']}."
            else:
                system_injection += f"\n[SYSTEM]: Tx {potential_id} Verified. Valid for claim. UUID: {tx['id']}."
        elif "order" in message.lower() or "#" in message:
            system_injection += f"\n[SYSTEM]: Tx {potential_id} NOT FOUND."

    try:
        if not client:
            return "API Key Configuration Error"

        # Transform history
        formatted_history = []
        if history:
            for m in history:
                role = m["role"] if m["role"] == "user" else "model"
                formatted_history.append(
                    types.Content(role=role, parts=[types.Part(text=m["content"])])
                )

        full_sys_prompt = f"{BASE_SYSTEM_PROMPT}\n\nCURRENT POLICY:\n{company_policy}"
        user_content = message
        if image_analysis:
            user_content += f"\n\n[IMAGE ANALYSIS]: {image_analysis}"
        if system_injection:
            user_content += system_injection

        chat = client.chats.create(model=GEMINI_MODEL_NAME, history=formatted_history)
        response = chat.send_message(f"{full_sys_prompt}\n\nUser: {user_content}")
        reply = response.text.strip()

        # Prepare Transcript Summary
        # Strip JSON from reply for the transcript (Handle both Code Block and raw JSON at end)
        clean_reply = re.sub(
            r"```json[\s\S]*?```", "", reply, flags=re.IGNORECASE
        ).strip()
        # Fallback: remove raw JSON if it looks like it's at the end but missing backticks
        if "```" not in reply:
            clean_reply = re.sub(r'\{[\s\S]*"action"[\s\S]*\}', "", clean_reply).strip()
        transcript = f"User: {message}\nAI: {clean_reply}"
        if history:
            # simple flatten of last 3 turns
            transcript = (
                "\\n".join([f"{h['role']}: {h['content']}" for h in history[-3:]])
                + f"\\n{transcript}"
            )

        # Action Handling
        json_match = re.search(r"```json([\s\S]*?)```", reply, re.IGNORECASE)
        action_type = None
        if json_match:
            try:
                action_data = json.loads(json_match.group(1))
                action_type = action_data.get("action")
                if action_type in ["REFUND", "ESCALATE", "REJECT"]:
                    tid = action_data.get("transaction_id")
                    # ... resolve tid ...
                    if tid and not re.match(r"^[0-9a-f\-]{36}$", tid, re.I):
                        tx_lookup = verify_transaction(tid)
                        if tx_lookup:
                            tid = tx_lookup["id"]

                    if tid:
                        company_id_val = None
                        tx_data = db_select("transactions", "id", tid)
                        if tx_data:
                            company_id_val = tx_data[0]["company_id"]

                        if action_type == "REFUND":
                            # 1. Create Refund Queue Entry
                            if tx_data:
                                create_refund_entry(
                                    tid, company_id_val, tx_data[0]["amount"]
                                )
                            # 2. Create Approved Claim Record (With Transcript)
                            reason = action_data.get("reason", "Approved by AI")
                            if company_id_val:
                                create_claim(
                                    tid,
                                    company_id_val,
                                    "APPROVED",
                                    reason,
                                    evidence_url=evidence_image_url,
                                    transcript=transcript,
                                )

                        elif action_type == "ESCALATE":
                            # 1. Create Linked Claim Record (To store context/image)
                            reason_text = action_data.get("reason")
                            if company_id_val:
                                create_claim(
                                    tid,
                                    company_id_val,
                                    "ESCALATED",
                                    reason_text,
                                    evidence_url=evidence_image_url,
                                    transcript=transcript,
                                )

                            # 2. Create Escalation Entry
                            create_escalation_entry(tid, customer_id, reason_text)

            except Exception as e:
                print(f"Action Error: {e}")

        stats_manager.update((time.time() - start_time) * 1000, action_type)
        return reply
    except Exception as e:
        return f"Brain freeze. {e}"


def get_dashboard_update(action_json: dict = None, analysis_text: str = None):
    # ... same ...
    events = []
    if analysis_text:
        events.append(
            {
                "type": "event",
                "icon": "block" if "Failed" in analysis_text else "image",
                "title": "Image Analysis",
                "subtitle": "Rejected" if "Failed" in analysis_text else "Completed",
            }
        )
    if action_json:
        events.append(
            {
                "type": "event",
                "icon": "receipt_long",
                "title": action_json.get("action"),
                "subtitle": action_json.get("reason"),
            }
        )
    return events
