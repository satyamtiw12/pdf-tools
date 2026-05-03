# 📄 PDFBox — Free PDF Tools Website

## 🗂️ Files

```
pdfbox/
├── index.html              ← Frontend
├── README.md               ← Yeh file
└── backend/
    ├── main.py             ← FastAPI (sab PDF logic)
    ├── requirements.txt    ← Python packages
    ├── Procfile            ← Railway ke liye
    ├── railway.toml        ← Railway config
    └── runtime.txt         ← Python 3.11
```

## 🚀 Railway Par Deploy (Step by Step)

### 1. GitHub par upload karein
- github.com par nayi repo banao: `pdfbox-backend`
- `backend/` folder ke 5 files upload karo

### 2. Railway par deploy karein
- railway.app → New Project → Deploy from GitHub
- Repo select karo → auto deploy hoga
- Settings → Domains → Generate Domain
- URL copy karo (jaise: `https://pdfbox.up.railway.app`)

### 3. Frontend update karein
`index.html` mein yeh line dhundho:
```js
const API_BASE = '';
```
Badlo:
```js
const API_BASE = 'https://YOUR-RAILWAY-URL.up.railway.app';
```

### 4. Frontend host karein
- Netlify.com par `index.html` drag & drop karo → free URL milega
- Ya GitHub Pages use karo

## 🖥️ Local Test Karna
```bash
cd backend
pip install -r requirements.txt
python main.py
# Chalta hai: http://localhost:8000
# API docs: http://localhost:8000/docs
```
`index.html` mein `API_BASE = 'http://localhost:8000'` set karo.

## 🛠️ 14 PDF Tools
Merge, Split, Compress, PDF↔JPG, Add Text, Signature, Highlight, Rotate, Delete Pages, Reorder, Password Protect, Unlock, PDF Info

## 💰 Cost: $0 — Bilkul Free!