#!/bin/bash
echo ""
echo "========================================"
echo "   PDFBox - Starting Server..."
echo "========================================"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 install nahi hai!"
    echo "Mac par: brew install python3"
    echo "Linux par: sudo apt install python3"
    exit 1
fi

# Install packages
echo "[1/3] Packages install ho rahe hain..."
pip3 install -r requirements.txt -q

echo "[2/3] Server start ho raha hai..."
echo ""
echo "----------------------------------------"
echo " Browser mein yeh URL open karein:"
echo " http://localhost:8000"
echo "----------------------------------------"
echo " Band karne ke liye: Ctrl+C dabayein"
echo "----------------------------------------"
echo ""

# Auto open browser
sleep 2 && (open "http://localhost:8000" 2>/dev/null || xdg-open "http://localhost:8000" 2>/dev/null) &

# Start server
python3 main.py