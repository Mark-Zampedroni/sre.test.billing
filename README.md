# Billing Extractor

A web application that extracts structured data from billing documents (PDFs and images), allows editing before confirmation, and visualizes the data.

## Features

- **Upload** billing PDFs and images (JPG, PNG, etc.)
- **Extract** vendor, amounts, dates, invoice numbers automatically
- **Edit** extracted data before confirmation
- **Dashboard** with statistics and recent uploads
- **REST API** for integrations

## Quick Start

### Docker (Recommended)

```bash
# Build combined frontend + backend image
docker build -t billing-extractor .

# Run on port 80
docker run -d -p 80:80 --name billing-app billing-extractor
```

### Development

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (serve static files)
cd frontend
python -m http.server 3000
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Container                      │
│                                                              │
│   ┌──────────────┐          ┌───────────────────────────┐   │
│   │    Nginx     │─────────▶│  Frontend (HTML/CSS/JS)   │   │
│   │   (port 80)  │          └───────────────────────────┘   │
│   │              │                                          │
│   │   /api/* ────┼─────────▶┌───────────────────────────┐   │
│   └──────────────┘          │  Backend (FastAPI/Uvicorn) │   │
│                             │       (port 8000)          │   │
│                             └───────────────────────────┘   │
│                                        │                     │
│                             ┌──────────┴──────────┐         │
│                             │    PDF/Image Parser  │         │
│                             │  (pdfplumber + PIL)  │         │
│                             └─────────────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/upload` | Upload PDF or image |
| GET | `/api/billings` | List all billings |
| GET | `/api/billings/{id}` | Get billing details |
| PUT | `/api/billings/{id}` | Update billing data |
| POST | `/api/billings/{id}/confirm` | Confirm billing |
| POST | `/api/billings/{id}/reject` | Reject billing |
| DELETE | `/api/billings/{id}` | Delete billing |
| GET | `/api/stats` | Get statistics |
| GET | `/health` | Health check |

## Deployment

See `terraform/` for AWS deployment (EC2 + ALB).

```bash
cd terraform
terraform init
terraform apply -var="vpc_id=vpc-xxx" -var='subnet_ids=["subnet-a","subnet-b"]'
```

## 🐛 Known Bug (Intentional - for SRE Testing)

This application contains an intentional critical bug for SRE/incident response training:

**Bug:** When processing a PDF with embedded images, or when uploading a CMYK image, the `process_images_in_pdf()` function crashes the entire backend process.

**Trigger:**
1. Upload a PDF that contains images
2. Upload a CMYK color-space image

**Effect:** The backend process crashes completely, not just returning a 500 error. This simulates a production incident where the service becomes unavailable.

**Location:** `backend/app/main.py` lines 196-230 (`process_images_in_pdf` function)

**Root Cause:** Attempting to open raw PDF stream bytes directly as PIL Image without proper format detection or error handling.
