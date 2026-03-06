"""
Billing Extractor API

Extracts structured data from billing PDFs and images using MiniMax AI.
Supports editing before confirmation.
"""

import os
import re
import uuid
import json
import base64
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pdfplumber
import aiosqlite
from PIL import Image
from openai import OpenAI
from dotenv import load_dotenv
import io

# Load environment variables
load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════════════

DATABASE_PATH = os.getenv("DATABASE_PATH", "/tmp/billings.db")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# MiniMax AI Configuration
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://bpod1.ai-factory.fastweb.it/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMaxAI/MiniMax-M2.5")

# Initialize OpenAI client for MiniMax (OpenAI-compatible API)
llm_client = None
if MINIMAX_API_KEY:
    llm_client = OpenAI(
        api_key=MINIMAX_API_KEY,
        base_url=MINIMAX_BASE_URL,
    )

app = FastAPI(title="Billing Extractor", version="2.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════════════════════════════════
# Models
# ══════════════════════════════════════════════════════════════════════════════

class LineItem(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: float


class BillingData(BaseModel):
    id: str
    filename: str
    file_type: str  # 'pdf' or 'image'
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: str = "EUR"
    line_items: List[LineItem] = []
    raw_text: str = ""
    status: str = "pending"  # pending, confirmed, rejected
    created_at: str
    confirmed_at: Optional[str] = None
    has_images: bool = False


class BillingUpdate(BaseModel):
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    currency: Optional[str] = None
    line_items: Optional[List[LineItem]] = None


class BillingSummary(BaseModel):
    id: str
    filename: str
    file_type: str
    vendor: Optional[str]
    total: Optional[float]
    date: Optional[str]
    status: str
    created_at: str


# ══════════════════════════════════════════════════════════════════════════════
# Database
# ══════════════════════════════════════════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS billings (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'pdf',
                vendor TEXT,
                invoice_number TEXT,
                date TEXT,
                due_date TEXT,
                subtotal REAL,
                tax REAL,
                total REAL,
                currency TEXT DEFAULT 'EUR',
                line_items TEXT,
                raw_text TEXT,
                status TEXT DEFAULT 'pending',
                has_images INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                confirmed_at TEXT
            )
        """)
        await db.commit()


async def save_billing(data: BillingData):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO billings (id, filename, file_type, vendor, invoice_number, date, due_date,
                                  subtotal, tax, total, currency, line_items, raw_text,
                                  status, has_images, created_at, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.id, data.filename, data.file_type, data.vendor, data.invoice_number,
            data.date, data.due_date, data.subtotal, data.tax, data.total,
            data.currency, json.dumps([item.dict() for item in data.line_items]),
            data.raw_text, data.status, 1 if data.has_images else 0,
            data.created_at, data.confirmed_at
        ))
        await db.commit()


async def update_billing(billing_id: str, updates: dict):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        set_clauses = []
        values = []
        for key, value in updates.items():
            if key == "line_items" and value is not None:
                value = json.dumps([item.dict() if hasattr(item, 'dict') else item for item in value])
            set_clauses.append(f"{key} = ?")
            values.append(value)
        
        values.append(billing_id)
        query = f"UPDATE billings SET {', '.join(set_clauses)} WHERE id = ?"
        await db.execute(query, values)
        await db.commit()


async def get_all_billings(status_filter: str = None) -> List[BillingSummary]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT id, filename, file_type, vendor, total, date, status, created_at FROM billings"
        params = []
        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)
        query += " ORDER BY created_at DESC"
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [BillingSummary(**dict(row)) for row in rows]


async def get_billing(billing_id: str) -> Optional[BillingData]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM billings WHERE id = ?", (billing_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                data = dict(row)
                data["line_items"] = json.loads(data["line_items"] or "[]")
                data["has_images"] = bool(data["has_images"])
                return BillingData(**data)
            return None


async def delete_billing(billing_id: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("DELETE FROM billings WHERE id = ?", (billing_id,))
        await db.commit()
        return cursor.rowcount > 0


# ══════════════════════════════════════════════════════════════════════════════
# AI Extraction with MiniMax
# ══════════════════════════════════════════════════════════════════════════════

EXTRACTION_PROMPT = """You are a billing data extraction assistant. Extract structured data from the following document text.

Return a JSON object with these fields:
- vendor: Company/vendor name (string or null)
- invoice_number: Invoice/document number (string or null)
- date: Invoice date in YYYY-MM-DD format (string or null)
- due_date: Due date in YYYY-MM-DD format (string or null)
- subtotal: Amount before tax (number or null)
- tax: Tax amount (number or null)
- total: Total amount (number or null)
- currency: Currency code, default "EUR" (string)
- line_items: Array of items, each with: description, quantity, unit_price, amount

Only return valid JSON, no markdown or explanation.

Document text:
"""


def extract_with_ai(raw_text: str) -> dict:
    """Use MiniMax AI to extract structured billing data from text."""
    
    if not llm_client:
        # Fallback to empty extraction if no API key configured
        return {
            "vendor": None,
            "invoice_number": None,
            "date": None,
            "due_date": None,
            "subtotal": None,
            "tax": None,
            "total": None,
            "currency": "EUR",
            "line_items": []
        }
    
    try:
        response = llm_client.chat.completions.create(
            model=MINIMAX_MODEL,
            messages=[
                {"role": "system", "content": "You are a precise data extraction assistant. Output only valid JSON."},
                {"role": "user", "content": EXTRACTION_PROMPT + raw_text[:8000]}
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Clean up potential markdown wrapping
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        
        return json.loads(result_text.strip())
    
    except Exception as e:
        print(f"AI extraction failed: {e}")
        # Return empty on failure
        return {
            "vendor": None,
            "invoice_number": None,
            "date": None,
            "due_date": None,
            "subtotal": None,
            "tax": None,
            "total": None,
            "currency": "EUR",
            "line_items": []
        }


# ══════════════════════════════════════════════════════════════════════════════
# Image Processing
# ══════════════════════════════════════════════════════════════════════════════

def process_images_in_pdf(pdf_path: str) -> dict:
    """
    Process images found in PDF for OCR extraction.
    Collects all images first, then processes them for text recognition.
    """
    image_data = {"count": 0, "extracted_text": []}
    
    # Collect all images for batch processing
    collected_images = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            if page.images:
                for img_info in page.images:
                    # Extract image from PDF
                    x0, y0, x1, y1 = img_info["x0"], img_info["top"], img_info["x1"], img_info["bottom"]
                    
                    # Crop page to image area and convert to PIL
                    cropped = page.within_bbox((x0, y0, x1, y1)).to_image(resolution=150)
                    pil_img = cropped.original
                    
                    # Convert to RGBA for consistent processing
                    rgba_img = pil_img.convert("RGBA")
                    
                    # Store raw pixel data for OCR pipeline
                    pixel_data = rgba_img.tobytes()
                    collected_images.append({
                        "page": page_num,
                        "pixels": pixel_data,
                        "size": rgba_img.size
                    })
                    
                    image_data["count"] += 1
    
    # Process collected images (OCR would go here)
    for idx, img_data in enumerate(collected_images):
        image_data["extracted_text"].append(
            f"Image {idx}: {img_data['size'][0]}x{img_data['size'][1]}"
        )
    
    return image_data


def extract_text_from_image(image_path: str) -> str:
    """
    Extract text from an image file.
    For now, returns placeholder - in production would use OCR.
    """
    with Image.open(image_path) as img:
        # Convert to RGB for consistency
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        # Placeholder for OCR
        width, height = img.size
        return f"[Image: {width}x{height} - OCR not implemented]"


# ══════════════════════════════════════════════════════════════════════════════
# Main Extraction Logic
# ══════════════════════════════════════════════════════════════════════════════

def extract_from_pdf(pdf_path: str, filename: str) -> BillingData:
    """Extract structured billing data from PDF using AI."""
    
    billing_id = str(uuid.uuid4())[:8]
    raw_text = ""
    has_images = False
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            raw_text += page_text + "\n"
            
            if page.images:
                has_images = True
    
    # 🐛 BUG TRIGGER: If PDF has images, crash the backend
    if has_images:
        image_info = process_images_in_pdf(pdf_path)
        raw_text += "\n--- Image Content ---\n"
        raw_text += "\n".join(image_info.get("extracted_text", []))
    
    # Use AI to extract structured data
    extracted = extract_with_ai(raw_text)
    
    # Parse line items
    line_items = []
    for item in extracted.get("line_items", []):
        try:
            line_items.append(LineItem(
                description=item.get("description", ""),
                quantity=item.get("quantity"),
                unit_price=item.get("unit_price"),
                amount=item.get("amount", 0)
            ))
        except:
            pass
    
    return BillingData(
        id=billing_id,
        filename=filename,
        file_type="pdf",
        vendor=extracted.get("vendor"),
        invoice_number=extracted.get("invoice_number"),
        date=extracted.get("date"),
        due_date=extracted.get("due_date"),
        subtotal=extracted.get("subtotal"),
        tax=extracted.get("tax"),
        total=extracted.get("total"),
        currency=extracted.get("currency", "EUR"),
        line_items=line_items,
        raw_text=raw_text[:10000],
        status="pending",
        has_images=has_images,
        created_at=datetime.utcnow().isoformat(),
        confirmed_at=None
    )


def extract_from_image(image_path: str, filename: str) -> BillingData:
    """Extract structured billing data from image."""
    
    billing_id = str(uuid.uuid4())[:8]
    
    # 🐛 BUG: Crashes on CMYK images
    raw_text = extract_text_from_image(image_path)
    
    # Use AI to extract (will return empty since OCR not implemented)
    extracted = extract_with_ai(raw_text)
    
    return BillingData(
        id=billing_id,
        filename=filename,
        file_type="image",
        vendor=extracted.get("vendor"),
        invoice_number=extracted.get("invoice_number"),
        date=extracted.get("date"),
        due_date=extracted.get("due_date"),
        subtotal=extracted.get("subtotal"),
        tax=extracted.get("tax"),
        total=extracted.get("total"),
        currency=extracted.get("currency", "EUR"),
        line_items=[],
        raw_text=raw_text[:10000],
        status="pending",
        has_images=True,
        created_at=datetime.utcnow().isoformat(),
        confirmed_at=None
    )


# ══════════════════════════════════════════════════════════════════════════════
# API Routes
# ══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    await init_db()


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "2.1.0",
        "ai_enabled": llm_client is not None,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.post("/api/upload")
async def upload_billing(file: UploadFile = File(...)):
    """Upload and process a billing PDF or image."""
    
    filename_lower = file.filename.lower()
    is_pdf = filename_lower.endswith('.pdf')
    is_image = any(filename_lower.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'])
    
    if not is_pdf and not is_image:
        raise HTTPException(status_code=400, detail="Supported formats: PDF, JPG, PNG, GIF, BMP, TIFF")
    
    # Save uploaded file
    ext = Path(file.filename).suffix
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}{ext}"
    content = await file.read()
    
    with open(file_path, "wb") as f:
        f.write(content)
    
    try:
        if is_pdf:
            billing = extract_from_pdf(str(file_path), file.filename)
        else:
            billing = extract_from_image(str(file_path), file.filename)
        
        await save_billing(billing)
        
        return {
            "success": True,
            "billing_id": billing.id,
            "data": billing.dict(),
            "message": "Data extracted. Please review and confirm."
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process file: {str(e)}")
    
    finally:
        if file_path.exists():
            file_path.unlink()


@app.get("/api/billings")
async def list_billings(status: str = None):
    """List all billings, optionally filtered by status."""
    billings = await get_all_billings(status)
    return {"billings": [b.dict() for b in billings]}


@app.get("/api/billings/{billing_id}")
async def get_billing_detail(billing_id: str):
    """Get billing details."""
    billing = await get_billing(billing_id)
    if not billing:
        raise HTTPException(status_code=404, detail="Billing not found")
    return billing.dict()


@app.put("/api/billings/{billing_id}")
async def update_billing_data(billing_id: str, updates: BillingUpdate):
    """Update billing data (for editing before confirmation)."""
    billing = await get_billing(billing_id)
    if not billing:
        raise HTTPException(status_code=404, detail="Billing not found")
    
    update_dict = {k: v for k, v in updates.dict().items() if v is not None}
    if update_dict:
        await update_billing(billing_id, update_dict)
    
    return {"success": True, "message": "Billing updated"}


@app.post("/api/billings/{billing_id}/confirm")
async def confirm_billing(billing_id: str):
    """Confirm billing data after review."""
    billing = await get_billing(billing_id)
    if not billing:
        raise HTTPException(status_code=404, detail="Billing not found")
    
    await update_billing(billing_id, {
        "status": "confirmed",
        "confirmed_at": datetime.utcnow().isoformat()
    })
    
    return {"success": True, "message": "Billing confirmed"}


@app.post("/api/billings/{billing_id}/reject")
async def reject_billing(billing_id: str):
    """Reject/discard billing."""
    billing = await get_billing(billing_id)
    if not billing:
        raise HTTPException(status_code=404, detail="Billing not found")
    
    await update_billing(billing_id, {"status": "rejected"})
    
    return {"success": True, "message": "Billing rejected"}


@app.delete("/api/billings/{billing_id}")
async def remove_billing(billing_id: str):
    """Delete a billing."""
    deleted = await delete_billing(billing_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Billing not found")
    return {"success": True}


@app.get("/api/stats")
async def get_stats():
    """Get billing statistics."""
    all_billings = await get_all_billings()
    confirmed = [b for b in all_billings if b.status == "confirmed"]
    pending = [b for b in all_billings if b.status == "pending"]
    
    total_confirmed = sum(b.total or 0 for b in confirmed)
    
    return {
        "total_billings": len(all_billings),
        "pending": len(pending),
        "confirmed": len(confirmed),
        "total_confirmed_amount": round(total_confirmed, 2),
        "currency": "EUR"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
