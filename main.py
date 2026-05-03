from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import uvicorn
import os, shutil, uuid, zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List
import threading, time, io

from pypdf import PdfReader, PdfWriter
from PIL import Image
import img2pdf
import fitz
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import A4, letter

app = FastAPI(title="PDFBox API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR   = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
FRONTEND   = BASE_DIR.parent / "index.html"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

MAX_FILE_MB   = 20
AUTO_DELETE_H = 2

def save_upload(file: UploadFile) -> Path:
    ext  = Path(file.filename).suffix or ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    dest = UPLOAD_DIR / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    size_mb = dest.stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        dest.unlink()
        raise HTTPException(400, f"File too large ({size_mb:.1f} MB). Max {MAX_FILE_MB} MB allowed.")
    return dest

def out_path(name: str) -> Path:
    return OUTPUT_DIR / f"{uuid.uuid4().hex}_{name}"

def parse_page_range(expr: str, total: int) -> List[int]:
    pages = set()
    for part in expr.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            try: pages.update(range(int(a)-1, int(b)))
            except: pass
        elif part.isdigit():
            pages.add(int(part)-1)
    return sorted(p for p in pages if 0 <= p < total)

def auto_cleaner():
    while True:
        cutoff = datetime.now() - timedelta(hours=AUTO_DELETE_H)
        for d in [UPLOAD_DIR, OUTPUT_DIR]:
            for f in d.iterdir():
                if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                    f.unlink(missing_ok=True)
        time.sleep(600)

threading.Thread(target=auto_cleaner, daemon=True).start()

# ── Serve Frontend ─────────────────────────────────────────────
@app.get("/")
async def root():
    if FRONTEND.exists():
        return FileResponse(FRONTEND)
    return {"message": "PDFBox API running! index.html same folder mein rakhein."}

@app.get("/health")
async def health():
    return {"status": "ok", "tools": 14, "max_file_mb": MAX_FILE_MB}

# ── 1. MERGE ───────────────────────────────────────────────────
@app.post("/api/merge")
async def merge_pdf(files: List[UploadFile] = File(...)):
    if len(files) < 2:
        raise HTTPException(400, "Kam se kam 2 PDF files chahiye.")
    paths = [save_upload(f) for f in files]
    writer = PdfWriter()
    for p in paths:
        for page in PdfReader(str(p)).pages:
            writer.add_page(page)
    out = out_path("merged.pdf")
    with open(out, "wb") as f: writer.write(f)
    for p in paths: p.unlink(missing_ok=True)
    return FileResponse(out, filename="merged.pdf", media_type="application/pdf")

# ── 2. SPLIT ───────────────────────────────────────────────────
@app.post("/api/split")
async def split_pdf(file: UploadFile = File(...), method: str = Form("each"), page_range: str = Form("")):
    path = save_upload(file)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    zip_out = out_path("split_pages.zip")
    with zipfile.ZipFile(zip_out, "w") as zf:
        if method == "each" or not page_range.strip():
            for i, page in enumerate(reader.pages):
                w = PdfWriter(); w.add_page(page)
                buf = io.BytesIO(); w.write(buf)
                zf.writestr(f"page_{i+1}.pdf", buf.getvalue())
        else:
            indices = parse_page_range(page_range, total)
            w = PdfWriter()
            for i in indices: w.add_page(reader.pages[i])
            buf = io.BytesIO(); w.write(buf)
            zf.writestr("selected_pages.pdf", buf.getvalue())
    path.unlink(missing_ok=True)
    return FileResponse(zip_out, filename="split_pages.zip", media_type="application/zip")

# ── 3. COMPRESS ────────────────────────────────────────────────
@app.post("/api/compress")
async def compress_pdf(file: UploadFile = File(...), level: str = Form("medium")):
    path = save_upload(file)
    orig_size = path.stat().st_size
    doc = fitz.open(str(path))
    dpi_map = {"low": 150, "medium": 100, "high": 60}
    dpi = dpi_map.get(level, 100)
    writer = fitz.open()
    for page in doc:
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        np = writer.new_page(width=page.rect.width, height=page.rect.height)
        np.insert_image(np.rect, pixmap=pix)
    out = out_path("compressed.pdf")
    writer.save(str(out), deflate=True, garbage=4)
    doc.close(); path.unlink(missing_ok=True)
    new_size = out.stat().st_size
    saved = round((1 - new_size/orig_size)*100) if orig_size > 0 else 0
    return FileResponse(out, filename="compressed.pdf", media_type="application/pdf",
                        headers={"X-Saved-Percent": str(saved)})

# ── 4. PDF TO JPG ──────────────────────────────────────────────
@app.post("/api/pdf-to-jpg")
async def pdf_to_jpg(file: UploadFile = File(...), quality: str = Form("medium")):
    path = save_upload(file)
    doc = fitz.open(str(path))
    dpi_map = {"low": 72, "medium": 150, "high": 300}
    mat = fitz.Matrix(dpi_map.get(quality, 150)/72, dpi_map.get(quality, 150)/72)
    zip_out = out_path("pdf_images.zip")
    with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=mat)
            zf.writestr(f"page_{i+1}.jpg", pix.tobytes("jpeg"))
    doc.close(); path.unlink(missing_ok=True)
    return FileResponse(zip_out, filename="pdf_images.zip", media_type="application/zip")

# ── 5. JPG TO PDF ──────────────────────────────────────────────
@app.post("/api/jpg-to-pdf")
async def jpg_to_pdf(files: List[UploadFile] = File(...), page_size: str = Form("a4")):
    paths = [save_upload(f) for f in files]
    out = out_path("images.pdf")
    if page_size == "auto":
        with open(out, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in paths]))
    else:
        size = A4 if page_size == "a4" else letter
        c = rl_canvas.Canvas(str(out), pagesize=size)
        W, H = size
        for p in paths:
            img = Image.open(p).convert("RGB")
            iw, ih = img.size
            ratio = min(W/iw, H/ih)
            nw, nh = iw*ratio, ih*ratio
            c.drawImage(str(p), (W-nw)/2, (H-nh)/2, nw, nh)
            c.showPage()
        c.save()
    for p in paths: p.unlink(missing_ok=True)
    return FileResponse(out, filename="converted.pdf", media_type="application/pdf")

# ── 6. ADD TEXT ────────────────────────────────────────────────
@app.post("/api/add-text")
async def add_text(file: UploadFile = File(...), text: str = Form(...),
                   page_num: int = Form(1), position: str = Form("bottom-center"),
                   font_size: int = Form(14), color: str = Form("#000000")):
    path = save_upload(file)
    doc = fitz.open(str(path))
    page_i = max(0, min(page_num-1, len(doc)-1))
    page = doc[page_i]
    W, H = page.rect.width, page.rect.height
    pos_map = {
        "top-left": (40,40), "top-center": (W/2,40), "top-right": (W-40,40),
        "center": (W/2,H/2),
        "bottom-left": (40,H-40), "bottom-center": (W/2,H-40), "bottom-right": (W-40,H-40),
    }
    x, y = pos_map.get(position, (W/2, H-40))
    hex_c = color.lstrip("#")
    r, g, b = tuple(int(hex_c[i:i+2], 16)/255 for i in (0,2,4))
    page.insert_text((x, y), text, fontsize=font_size, color=(r,g,b), overlay=True)
    out = out_path("text_added.pdf")
    doc.save(str(out)); doc.close(); path.unlink(missing_ok=True)
    return FileResponse(out, filename="text_added.pdf", media_type="application/pdf")

# ── 7. ADD SIGNATURE ───────────────────────────────────────────
@app.post("/api/add-signature")
async def add_signature(file: UploadFile = File(...), sig_text: str = Form(""),
                        page_num: int = Form(-1),
                        sig_image: Optional[UploadFile] = File(None)):
    path = save_upload(file)
    doc = fitz.open(str(path))
    page_i = len(doc)-1 if page_num == -1 else max(0, page_num-1)
    page = doc[page_i]
    W, H = page.rect.width, page.rect.height
    if sig_image and sig_image.filename:
        img_path = save_upload(sig_image)
        page.insert_image(fitz.Rect(W-200, H-80, W-20, H-20), filename=str(img_path))
        img_path.unlink(missing_ok=True)
    elif sig_text:
        page.insert_text((W-200, H-30), sig_text, fontsize=18, color=(0.1,0.1,0.6), overlay=True)
    out = out_path("signed.pdf")
    doc.save(str(out)); doc.close(); path.unlink(missing_ok=True)
    return FileResponse(out, filename="signed.pdf", media_type="application/pdf")

# ── 8. HIGHLIGHT ───────────────────────────────────────────────
@app.post("/api/highlight")
async def highlight_text(file: UploadFile = File(...), search_text: str = Form(...),
                         color: str = Form("yellow")):
    color_map = {"yellow":(1,1,0),"green":(0,1,0.5),"blue":(0.5,0.8,1),"pink":(1,0.5,0.8),"orange":(1,0.7,0.2)}
    rgb = color_map.get(color, (1,1,0))
    path = save_upload(file)
    doc = fitz.open(str(path))
    for page in doc:
        for rect in page.search_for(search_text):
            annot = page.add_highlight_annot(rect)
            annot.set_colors(stroke=rgb); annot.update()
    out = out_path("highlighted.pdf")
    doc.save(str(out)); doc.close(); path.unlink(missing_ok=True)
    return FileResponse(out, filename="highlighted.pdf", media_type="application/pdf")

# ── 9. ROTATE ──────────────────────────────────────────────────
@app.post("/api/rotate")
async def rotate_pdf(file: UploadFile = File(...), degrees: int = Form(90), apply_to: str = Form("all")):
    path = save_upload(file)
    reader = PdfReader(str(path)); writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if apply_to == "all" or (apply_to == "first" and i == 0):
            page.rotate(degrees)
        writer.add_page(page)
    out = out_path("rotated.pdf")
    with open(out, "wb") as f: writer.write(f)
    path.unlink(missing_ok=True)
    return FileResponse(out, filename="rotated.pdf", media_type="application/pdf")

# ── 10. DELETE PAGES ───────────────────────────────────────────
@app.post("/api/delete-pages")
async def delete_pages(file: UploadFile = File(...), pages: str = Form(...)):
    path = save_upload(file)
    reader = PdfReader(str(path))
    to_del = set(parse_page_range(pages, len(reader.pages)))
    writer = PdfWriter()
    for i, page in enumerate(reader.pages):
        if i not in to_del: writer.add_page(page)
    if not writer.pages:
        raise HTTPException(400, "Kam se kam ek page rehna chahiye!")
    out = out_path("pages_deleted.pdf")
    with open(out, "wb") as f: writer.write(f)
    path.unlink(missing_ok=True)
    return FileResponse(out, filename="pages_deleted.pdf", media_type="application/pdf")

# ── 11. REORDER ────────────────────────────────────────────────
@app.post("/api/reorder")
async def reorder_pages(file: UploadFile = File(...), order: str = Form(...)):
    path = save_upload(file)
    reader = PdfReader(str(path))
    total = len(reader.pages)
    indices = [int(x.strip())-1 for x in order.split(",") if x.strip().isdigit()]
    indices = [i for i in indices if 0 <= i < total]
    if not indices: raise HTTPException(400, "Valid page numbers likhein.")
    writer = PdfWriter()
    for i in indices: writer.add_page(reader.pages[i])
    out = out_path("reordered.pdf")
    with open(out, "wb") as f: writer.write(f)
    path.unlink(missing_ok=True)
    return FileResponse(out, filename="reordered.pdf", media_type="application/pdf")

# ── 12. PROTECT ────────────────────────────────────────────────
@app.post("/api/protect")
async def protect_pdf(file: UploadFile = File(...), password: str = Form(...)):
    if len(password) < 4: raise HTTPException(400, "Min 4 characters ka password chahiye.")
    path = save_upload(file)
    reader = PdfReader(str(path)); writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    writer.encrypt(password)
    out = out_path("protected.pdf")
    with open(out, "wb") as f: writer.write(f)
    path.unlink(missing_ok=True)
    return FileResponse(out, filename="protected.pdf", media_type="application/pdf")

# ── 13. UNLOCK ─────────────────────────────────────────────────
@app.post("/api/unlock")
async def unlock_pdf(file: UploadFile = File(...), password: str = Form(...)):
    path = save_upload(file)
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if not reader.decrypt(password):
            path.unlink(missing_ok=True)
            raise HTTPException(400, "Password galat hai!")
    writer = PdfWriter()
    for page in reader.pages: writer.add_page(page)
    out = out_path("unlocked.pdf")
    with open(out, "wb") as f: writer.write(f)
    path.unlink(missing_ok=True)
    return FileResponse(out, filename="unlocked.pdf", media_type="application/pdf")

# ── 14. PDF INFO ───────────────────────────────────────────────
@app.post("/api/info")
async def pdf_info(file: UploadFile = File(...)):
    path = save_upload(file)
    reader = PdfReader(str(path))
    info = reader.metadata or {}
    result = {
        "pages": len(reader.pages),
        "file_size_kb": path.stat().st_size // 1024,
        "title": str(info.get("/Title", "N/A")),
        "author": str(info.get("/Author", "N/A")),
        "encrypted": reader.is_encrypted,
    }
    path.unlink(missing_ok=True)
    return JSONResponse(result)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*45}")
    print(f"  PDFBox Server Chal Raha Hai!")
    print(f"{'='*45}")
    print(f"  Browser mein kholein: http://localhost:{port}")
    print(f"  API Docs:             http://localhost:{port}/docs")
    print(f"  Band karna:           Ctrl+C")
    print(f"{'='*45}\n")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)