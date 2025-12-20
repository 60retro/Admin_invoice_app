import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
from io import BytesIO
import requests
import base64
import time
import math
import os
import tempfile
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import re

# ==========================================
# ⚙️ 1. Config & Embedded Logo
# ==========================================
st.set_page_config(page_title="Nami Admin V113", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 URL เดิม
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# 🖼️ Embedded Logo (Base64)
# This is the exact data string you provided.
LOGO_BASE64_STR = "data:image/jpeg;base64,/9j/4QFTRXhpZgAATU0AKgAAAAgABgEAAAQAAAABAAASWAEBAAQAAAABAAAHIAExAAIAAAApAAAAVodpAAQAAAABAAAAkwESAAMAAAABAAAAAAEyAAIAAAAUAAAAfwAAAABBbmRyb2lkIEJQMkEuMjUwNjA1LjAzMS5BMy5TOTM4QlhYUzdCWUszADIwMjU6MTI6MDQgMTM6MzU6MDUAAASQAwACAAAAFAAAAMmSkQACAAAABDEzNACQEQACAAAABwAAAN2SCAADAAAAAQAAAAAAAAAAMjAyNToxMjowNCAxMzozNTowNQArMDc6MDAAAAMBMQACAAAAKQAAAQ4BEgADAAAAAQAAAAABMgACAAAAFAAAATcAAAAAQW5kcm9pZCBCUDJBLjI1MDYwNS4wMzEuQTMuUzkzOEJYWFM3QllLMwAyMDI1OjEyOjA0IDEzOjM1OjA1AP/iAhhJQ0NfUFJPRklMRQABAQAAAggAAAAABDAAAG1udHJSR0IgWFlaIAfgAAEAAQAAAAAAAGFjc3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAD21gABAAAAANMtAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAACWRlc2MAAADwAAAAZHJYWVoAAAFUAAAAFGdYWVoAAAFoAAAAFGJYWVoAAAF8AAAAFHd0cHQAAAGQAAAAFHJUUkMAAAGkAAAAKGdUUkMAAAGkAAAAKGJUUkMAAAGkAAAAKGNwcnQAAAHMAAAAPG1sdWMAAAAAAAAAAQAAAAxlblVTAAAARgAAABwARABpAHMAcABsAGEAeQAgAFAAMwAgAEcAYQBtAHUAdAAgAHcAaQB0AGgAIABzAFIARwBCACAAVAByAGEAbgBzAGYAZQByAABYWVogAAAAAAAAg90AAD2+////u1hZWiAAAAAAAABKvwAAsTcAAAq5WFlaIAAAAAAAACg7AAARCwAAyMtYWVogAAAAAAAA9tYAAQAAAADTLXBhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADb/4AAQSkZJRgABAQIAOwA7AAD/2wBDAAIBAQEBAQIBAQECAgICAgQDAgICAgUEBAMEBgUGBgYFBgYGBwkIBgcJBwYGCAsICQoKCgoKBggLDAsKDAkKCgr/2wBDAQICAgICAgUDAwUKBwYHCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgr/wAARCAcgElgDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/90ABAEm/9oADAMBAAIRAxEAPwD9/MDOaKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD/9D9/KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigD/9X9/KKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKAP/0f38ooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooA//9k="

# Helper Function to handle Base64 image
def save_logo_to_tempfile(b64_string):
    """
    Decodes a base64 string and saves it as a temporary image file.
    Returns the file path.
    """
    if "," in b64_string:
        b64_string = b64_string.split(",")[1]
    
    try:
        image_data = base64.b64decode(b64_string)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
            temp_file.write(image_data)
            return temp_file.name
    except Exception as e:
        st.error(f"Error loading embedded logo: {e}")
        return None

# Load Font
try:
    # Register the font if it exists
    if os.path.exists('THSarabunNewBold.ttf'):
        pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
        FONT_NAME = 'CustomFont'
    else:
        # Fallback to standard font if Thai font is missing
        FONT_NAME = 'Helvetica'
        st.warning("⚠️ ไม่พบไฟล์ฟอนต์ 'THSarabunNewBold.ttf' การแสดงผลภาษาไทยอาจไม่ถูกต้อง")
except:
    FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. Smart Connection
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def smart_request(func, *args):
    """Auto-retry when Google blocks (Quota Exceeded)"""
    for i in range(3):
        try: return func(*args)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e): time.sleep(2); continue
            raise e
    return func(*args)

@st.cache_data(ttl=300)
def load_static_data():
    try:
        client = get_client(); sh = client.open(SHEET_NAME)
        items = smart_request(lambda: pd.DataFrame(sh.worksheet("Items").get_all_records()))
        custs = smart_request(lambda: pd.DataFrame(sh.worksheet("Customers").get_all_records()))
        return items, custs
    except: return pd.DataFrame(), pd.DataFrame()

def load_live_data():
    client = get_client(); sh = client.open(SHEET_NAME)
    ws_conf = sh.worksheet("Config")
    data = smart_request(ws_conf.get_all_values)
    conf = {str(r[0]): str(r[1]) for r in data if len(r) >= 2}
    try: ws_q = sh.worksheet("Queue")
    except: ws_q = None
    return sh, ws_conf, conf, ws_q

def upload_via_webhook(pdf_bytes, filename):
    try:
        payload = {"filename": filename, "mimeType": "application/pdf", "file": base64.b64encode(pdf_bytes).decode('utf-8'), "folderId": DRIVE_FOLDER_ID}
        requests.post(APPS_SCRIPT_URL, json=payload)
        return True
    except: return False

# ==========================================
# 🖨️ 3. PDF Generator (Copy from Desktop V87)
# ==========================================
def generate_pdf_v87_exact(doc_data, items, doc_type, run_no, date_str, vat_inc, logo_path):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4; half_height = height / 2

    # 1. Calc Total Logic (Same as Desktop)
    total = sum([x['qty'] * x['price'] for x in items])
    if vat_inc:
        g = total; s = total / 1.07; v = g - s
    else:
        s = total; v = total * 0.07; g = s + v
        g = math.floor(g) # Desktop logic

    def wrap_text_lines(text, width_limit, font_name, font_size):
        c.setFont(font_name, font_size)
        words = str(text).split(' ')
        lines = []; current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            w = pdfmetrics.stringWidth(test_line, font_name, font_size)
            if w <= width_limit: current_line.append(word)
            else:
                if current_line: lines.append(' '.join(current_line)); current_line = [word]
                else: lines.append(word); current_line = []
        if current_line: lines.append(' '.join(current_line))
        return lines if lines else [""]

    def draw_invoice(y_offset):
        # 🟢 Variables from Desktop V87
        margin = 15 * mm
        base_y = y_offset
        top_y = base_y + half_height - margin
        page_w = width - (2 * margin)
        font_std = 11; font_bold = 12; line_h = 12
        
        # Logo
        logo_w = 110; logo_h = 55
        if logo_path and os.path.exists(logo_path):
            try:
                # Use ImageReader with file path
                img = ImageReader(logo_path)
                c.drawImage(img, margin, top_y - logo_h + 5, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
            except Exception as e:
                print(f"Logo draw error: {e}")

        # Shop Box
        box_w = 260; box_h = 80
        box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        
        c.setFont(FONT_NAME, font_bold)
        c.drawString(box_x + 10, box_y + box_h - 15, doc_data['s_n'])
        
        c.setFont(FONT_NAME, font_std)
        raw_addr = doc_data['s_a'].split('\n')
        cur_sy = box_y + box_h - 30
        for line in raw_addr:
            wrapped = wrap_text_lines(line, box_w - 20, FONT_NAME, font_std)
            for w in wrapped:
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w); cur_sy -= line_h

        # Title
        t_str = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        full_title = f"ต้นฉบับ {t_str}" if y_offset > 0 else f"สำเนา {t_str}"
        if doc_type == "ABB": full_title = t_str

        title_y = box_y - 20
        c.setFont(FONT_NAME, font_bold + 2)
        center_x_left = margin + ((box_x - margin) / 2)
        c.drawCent
