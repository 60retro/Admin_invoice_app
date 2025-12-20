import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
from io import BytesIO
import requests
import base64
import math
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import re

# ==========================================
# ⚙️ 1. Config & Setup (คงเดิมจาก V87)
# ==========================================
st.set_page_config(page_title="Nami V87 Web Port", layout="wide", page_icon="🧾")

# 🟢 ตั้งค่าส่วนตัว
ADMIN_PASSWORD = "3457"
SHEET_NAME = "Invoice_Data"
# ใส่ URL Webhook ที่คุณทำไว้ (เพื่อแก้ปัญหา Backup 403)
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" 
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur" 

# Load Fonts (เหมือน V87)
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME_STD = 'CustomFont'
    FONT_NAME_BOLD = 'CustomFont' # ใช้ตัวหนาตัวเดียวกันถ้าไม่มีไฟล์แยก
except:
    FONT_NAME_STD = 'Helvetica'
    FONT_NAME_BOLD = 'Helvetica-Bold'

# ==========================================
# 🔌 2. Database Connection
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def load_data():
    client = get_client()
    sh = client.open(SHEET_NAME)
    return sh

# ==========================================
# 🖨️ 3. PDF Engine (COPY จาก V87 100%)
# ==========================================
def generate_pdf_v87_logic(doc_data, items, doc_type, running_no, date_str, vat_inc):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    half_height = height / 2

    # --- Helper: Wrap Text (Logic เดิม) ---
    def wrap_text_lines(text, width_limit, font_name, font_size):
        c.setFont(font_name, font_size)
        words = str(text).split(' ')
        lines = []
        current_line = []
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
        # 🟢 ตัวแปรตำแหน่ง (Copy จาก V87 เป๊ะๆ)
        margin = 15 * mm
        base_y = y_offset
        top_y = base_y + half_height - margin
        page_w = width - (2 * margin)
        font_size_std = 11
        font_size_bold = 12
        line_height = 12
        
        # --- Header ---
        # (ส่วน Logo ตัดออก หรือใส่ถ้ามีไฟล์)
        
        # Shop Box
        box_w = 260; box_h = 80 
        box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        
        c.setFont(FONT_NAME_BOLD, font_size_bold)
        c.drawString(box_x + 10, box_y + box_h - 15, doc_data['s_n']) # Shop Name
        
        c.setFont(FONT_NAME_STD, font_size_std)
        raw_addr = doc_data['s_a'].split('\n')
        cur_sy = box_y + box_h - 30
        for line in raw_addr:
            wrapped_lines = wrap_text_lines(line, box_w - 20, FONT_NAME_STD, font_size_std)
            for w_line in wrapped_lines:
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w_line); cur_sy -= line_height

        # Title
        title_txt = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        full_title = f"ต้นฉบับ {title_txt}" if y_offset > 0 else f"สำเนา {title_txt}"
        
        title_y = box_y - 20; center_x_left = margin + ((box_x - margin) / 2)
        c.setFont(FONT_NAME_BOLD, font_size_bold + 2)
        c.drawCentredString(center_x_left, title_y, full_title)
        
        bar_y = title_y - 20 
        c.setFont(FONT_NAME_BOLD, font_size_std)
        c.drawString(margin, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['s_t']}") # Shop Tax
        c.drawRightString(width - margin, bar_y, f"เลขที่ : {running_no}")
        
        # --- Customer Box ---
        info_box_y = bar_y - 5; info_box_h = 75; info_box_btm = info_box_y - info_box_h
        c.rect(margin, info_box_btm, page_w, info_box_h)
        div_x = width - margin - 200
        c.line(div_x, info_box_y, div_x, info_box_btm)
        
        c.setFont(FONT_NAME_BOLD, font_size_std); cx = margin + 10; cy = info_box_y - 12; label_gap = 12; label_anchor = cx + 110 
        c.drawRightString(label_anchor, cy, f"เลขประจำตัวผู้เสียภาษีอากร :"); c.setFont(FONT_NAME_STD, font_size_std)
        if doc_data['c_t']: c.drawString(label_anchor + 5, cy, doc_data['c_t'])
        current_y = cy - label_gap 

        c.setFont(FONT_NAME_BOLD, font_size_std); c.drawRightString(label_anchor, current_y, f"ชื่อลูกค้า :")
        c.setFont(FONT_NAME_STD, font_size_std)
        
        # 🔴 FIX V87: คำนวณความกว้างที่แท้จริง
        available_width = div_x - (label_anchor + 5) - 5
        cust_name_lines = wrap_text_lines(doc_data['c_n'], available_width, FONT_NAME_STD, font_size_std)
        for line in cust_name_lines:
            c.drawString(label_anchor + 5, current_y, line); current_y -= 10
        current_y -= 2

        c.setFont(FONT_NAME_BOLD, font_size_std); c.drawRightString(label_anchor, current_y, f"ที่อยู่ :")
        c.setFont(FONT_NAME_STD, font_size_std)
        
        addr_lines = wrap_text_lines(doc_data['c_a'], available_width, FONT_NAME_STD, font_size_std)
        for line in addr_lines:
            c.drawString(label_anchor + 5, current_y, line); current_y -= 10
        
        tel_y = info_box_btm + 5
        c.setFont(FONT_NAME_BOLD, font_size_std); c.drawRightString(label_anchor, tel_y, f"โทรศัพท์ :")
        c.setFont(FONT_NAME_STD, font_size_std); c.drawString(label_anchor + 5, tel_y, doc_data['c_tel'])

        dx = div_x + 10; dy = info_box_y - 12
        c.setFont(FONT_NAME_BOLD, font_size_std)
        c.drawRightString(dx + 80, dy, f"วันที่เอกสาร :"); c.drawRightString(dx + 80, dy - label_gap, f"พนักงานขาย :"); c.drawRightString(dx + 80, dy - label_gap*2, f"เงื่อนไขการชำระ :")
        c.setFont(FONT_NAME_STD, font_size_std)
        c.drawString(dx + 85, dy, date_str); c.drawString(dx + 85, dy - label_gap*2, "สด")

        # --- TABLE ---
        tbl_top = info_box_btm - 5
        c.setFillColorRGB(0.2, 0.2, 0.2); c.rect(margin, tbl_top - 14, page_w, 14, fill=1, stroke=1)
        c.setFillColorRGB(1, 1, 1)
        # 🔴 Col Widths from V87
        col_w = [25, page_w - 215, 45, 70, 75] 
        col_x = [margin, margin+col_w[0], margin+col_w[0]+col_w[1], margin+col_w[0]+col_w[1]+col_w[2], margin+col_w[0]+col_w[1]+col_w[2]+col_w[3]]
        
        c.setFont(FONT_NAME_BOLD, font_size_std)
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]
        for i, h in enumerate(headers):
            c.drawCentredString(col_x[i] + col_w[i]/2, tbl_top - 10, h)
        c.setFillColorRGB(0, 0, 0)
        
        current_y = tbl_top - 14
        c.setFont(FONT_NAME_STD, font_size_std)
        
        for idx, item in enumerate(items, start=1):
            if idx > 15: break
            name = item['name']; qty = item['qty']; price = item['price']
            
            # Logic ตัดคำสินค้าเหมือน V87
            name_lines = wrap_text_lines(str(name), col_w[1] - 10, FONT_NAME_STD, font_size_std)
            if len(name_lines) > 3: name_lines = name_lines[:3]
            row_h = 45 
            
            text_top_y = current_y - 12
            c.drawCentredString(col_x[0] + col_w[0]/2, text_top_y, str(idx))
            for i, line in enumerate(name_lines): c.drawString(col_x[1] + 5, text_top_y - (i * 12), line)
            c.drawRightString(col_x[2] + col_w[2] - 10, text_top_y, f"{qty:,.0f}")
            c.drawRightString(col_x[3] + col_w[3] - 5, text_top_y, f"{price:,.2f}")
            c.drawRightString(col_x[4] + col_w[4] - 5, text_top_y, f"{qty*price:,.2f}")
            current_y -= row_h
            c.setLineWidth(0.5); c.line(margin, current_y, width - margin, current_y)
        
        table_btm = current_y
        c.rect(margin, table_btm, page_w, (tbl_top - 14) - table_btm)
        for x in col_x[1:]: c.line(x, tbl_top - 14, x, table_btm)
        
        # Footer & Sig
        # 🔴 คำนวณ VAT ตาม Logic V87
        total = sum([x['qty']*x['price'] for x in items])
        if vat_inc:
            g=total; s=total/1.07; v=g-s
        else:
            s=total; v=total*0.07; g=s+v; g=math.floor(g)

        footer_labels = ["จำนวนเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        footer_values = [f"{s+v:,.2f}", "-", f"{s:,.2f}", f"{v:,.2f}", f"{g:,.2f}"]
        
        footer_row_h = 14; footer_top = table_btm; footer_rows = 5
        c.line(col_x[4], footer_top, col_x[4], footer_top - (footer_rows * footer_row_h)) 
        c.line(width - margin, footer_top, width - margin, footer_top - (footer_rows * footer_row_h)) 
        for i in range(footer_rows):
            row_top = footer_top - (i * footer_row_h); row_btm = row_top - footer_row_h; text_y = row_btm + 4
            c.line(col_x[4], row_btm, width - margin, row_btm)
            c.setFont(FONT_NAME_BOLD, font_size_std); c.drawRightString(col_x[4] - 15, text_y, footer_labels[i] + " :")
            if i == 4: c.setFont(FONT_NAME_BOLD, font_size_bold)
            else: c.setFont(FONT_NAME_STD, font_size_std)
            c.drawRightString(width - margin - 5, text_y, footer_values[i])

        footer_btm_y = footer_top - (footer_rows * footer_row_h); sig_y = footer_btm_y - 25
        c.setFont(FONT_NAME_BOLD, font_size_std)
        c.drawString(margin + 20, sig_y, f"ผู้รับสินค้า ...........................................................")
        c.drawString(width - margin - 220, sig_y, f"ผู้รับเงิน ...........................................................")

    # 🟢 Logic วาด 2 ท่อน (เหมือน V87)
    if doc_type == "ABB":
        draw_invoice(half_height)
    else:
        draw_invoice(half_height) # บน (Original)
        c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0) # เส้นประ
        draw_invoice(0) # ล่าง (Copy)

    c.save()
    buffer.seek(0)
    return buffer, g

def upload_to_drive_webhook(pdf_bytes, filename):
    try:
        payload = {
            "filename": filename, "mimeType": "application/pdf",
            "file": base64.b64encode(pdf_bytes).decode('utf-8'), "folderId": DRIVE_FOLDER_ID
        }
        requests.post(APPS_SCRIPT_URL, json=payload)
        return True
    except: return False

# ==========================================
# 🖥️ 4. UI Implementation (State Management)
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
# Form Vars
for k in ['s_n', 's_t', 's_a', 'c_n', 'c_t', 'c_a1', 'c_a2', 'c_tel', 'doc_no']:
    if k not in st.session_state: st.session_state[k] = ""

# Login Screen
if not st.session_state.logged_in:
    st.title("🔒 Login V87 Port")
    pwd = st.text_input("Password", type="password")
    if st.button("Enter"):
        if pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
        else: st.error("Wrong Password")
    st.stop()

# --- Load Data into Session State (Sync) ---
def sync_db():
    try:
        sh = load_data()
        # Config
        ws_conf = sh.worksheet("Config")
        conf = dict(ws_conf.get_all_values())
        st.session_state.s_n = conf.get("ShopName","")
        st.session_state.s_t = conf.get("TaxID","")
        st.session_state.s_a = conf.get("Address","")
        st.session_state.full_run = conf.get("Full_No","")
        st.session_state.abb_run = conf.get("Abb_No","")
        
        # Customers & Items
        st.session_state.db_cust = pd.DataFrame(sh.worksheet("Customers").get_all_records())
        st.session_state.db_item = pd.DataFrame(sh.worksheet("Items").get_all_records())
        st.toast("Sync Completed!")
    except Exception as e: st.error(f"Sync Error: {e}")

if 'db_cust' not in st.session_state: sync_db()

# ==========================================
# 🖥️ 5. Layout (เหมือน V87 UI)
# ==========================================
st.sidebar.title("Menu")
if st.sidebar.button("🔄 Sync DB (ดึงข้อมูลล่าสุด)"): sync_db()

st.title("🧾 Invoice Generator (V87 Logic)")

# --- 1. Shop Info ---
with st.expander("🔒 ข้อมูลผู้ขาย (Editable)", expanded=True):
    c1, c2 = st.columns(2)
    st.session_state.s_n = c1.text_input("ชื่อร้าน", st.session_state.s_n)
    st.session_state.s_t = c2.text_input("Tax ID", st.session_state.s_t)
    st.session_state.s_a = st.text_area("ที่อยู่", st.session_state.s_a, height=80)
    
    if st.button("บันทึกข้อมูลร้าน"):
        sh = load_data(); ws = sh.worksheet("Config")
        cell = ws.find("ShopName"); ws.update_cell(cell.row, 2, st.session_state.s_n)
        cell = ws.find("TaxID"); ws.update_cell(cell.row, 2, st.session_state.s_t)
        cell = ws.find("Address"); ws.update_cell(cell.row, 2, st.session_state.s_a)
        st.success("Saved Config!")

# --- 2. Customer & Doc ---
c_left, c_right = st.columns([1.5, 1])

with c_left:
    st.subheader("ข้อมูลลูกค้า")
    # Search
    cust_list = [""] + list(st.session_state.db_cust['Name'].unique()) if not st.session_state.db_cust.empty else []
    sel_c = st.selectbox("ค้นหาลูกค้า", cust_list)
    if sel_c and sel_c != st.session_state.get('last_c'):
        row = st.session_state.db_cust[st.session_state.db_cust['Name']==sel_c].iloc[0]
        st.session_state.c_n = row['Name']; st.session_state.c_t = str(row['TaxID'])
        st.session_state.c_a1 = row['Address1']; st.session_state.c_a2 = row['Address2']; st.session_state.c_tel = str(row['Phone'])
        st.session_state.last_c = sel_c; st.rerun()

    c1, c2 = st.columns(2)
    st.session_state.c_n = c1.text_input("ชื่อ", st.session_state.c_n)
    st.session_state.c_t = c2.text_input("Tax", st.session_state.c_t)
    st.session_state.c_a1 = st.text_input("ที่อยู่ 1", st.session_state.c_a1)
    st.session_state.c_a2 = st.text_input("ที่อยู่ 2", st.session_state.c_a2)
    st.session_state.c_tel = st.text_input("โทร", st.session_state.c_tel)
    
    if st.button("💾 จำค่าลูกค้า"):
        sh = load_data(); sh.worksheet("Customers").append_row([st.session_state.c_n, st.session_state.c_t, st.session_state.c_a1, st.session_state.c_a2, st.session_state.c_tel])
        st.success("Saved Customer")

with c_right:
    st.subheader("เอกสาร")
    doc_type = st.radio("Type", ["Full", "ABB"], horizontal=True)
    # Logic Running No (เหมือน V87)
    curr = st.session_state.full_run if doc_type == "Full" else st.session_state.abb_run
    run_no = st.text_input("เลขที่", value=curr)
    d_date = st.date_input("วันที่", datetime.now())
    vat_inc = st.checkbox("ราคารวม VAT แล้ว", value=True)

# --- 3. Items ---
st.divider()
st.subheader("รายการสินค้า")
i1, i2, i3, i4 = st.columns([3, 1, 1, 1])
item_list = [""] + list(st.session_state.db_item['ItemName'].unique()) if not st.session_state.db_item.empty else []
sel_i = i1.selectbox("เลือกสินค้า", item_list)
qty = i2.number_input("Qty", 1, value=1)
price = i3.number_input("Price", 0.0)
if i4.button("Add"):
    if sel_i: st.session_state.cart.append({"name": sel_i, "qty": qty, "price": price})

if st.session_state.cart:
    df_cart = pd.DataFrame(st.session_state.cart)
    df_cart['Total'] = df_cart['qty'] * df_cart['price']
    st.dataframe(df_cart, use_container_width=True)
    
    if st.button("❌ ลบรายการล่าสุด"): st.session_state.cart.pop(); st.rerun()
    
    st.markdown("---")
    use_backup = st.checkbox("Backup to Drive", value=True)
    
    if st.button("🖨️ Print PDF & Save", type="primary"):
        if not st.session_state.c_n: st.error("ระบุลูกค้าก่อน")
        else:
            with st.spinner("Generating..."):
                # Data Prep
                d_data = {
                    's_n': st.session_state.s_n, 's_t': st.session_state.s_t, 's_a': st.session_state.s_a,
                    'c_n': st.session_state.c_n, 'c_t': st.session_state.c_t, 'c_a': f"{st.session_state.c_a1} {st.session_state.c_a2}", 'c_tel': st.session_state.c_tel
                }
                
                # 1. Gen PDF (ใช้ Logic V87)
                pdf_bytes, grand_total = generate_pdf_v87_logic(d_data, st.session_state.cart, doc_type, run_no, str(d_date), vat_inc)
                fname = f"INV_{run_no}.pdf"
                
                # 2. Update Sheet
                try:
                    sh = load_data()
                    # Run No
                    prefix = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if prefix:
                        nxt = f"{prefix.group(1)}{str(int(prefix.group(2))+1).zfill(len(prefix.group(2)))}"
                        wk = sh.worksheet("Config")
                        key = "Full_No" if doc_type == "Full" else "Abb_No"
                        cell = wk.find(key); wk.update_cell(cell.row, 2, nxt)
                    
                    # Sales Log
                    sh.worksheet("SalesLog").append_row([str(d_date), run_no, st.session_state.c_n, grand_total])
                except: st.warning("Sheet Update Error")
                
                # 3. Backup
                msg = ""
                if use_backup:
                    if upload_to_drive_webhook(pdf_bytes.getvalue(), fname): msg = "Backup OK"
                    else: msg = "Backup Failed"
                
                st.success(f"Success! {msg}")
                st.download_button("Download PDF", pdf_bytes, fname, "application/pdf")
                st.session_state.cart = [] # Clear

# --- Sidebar Queue ---
with st.sidebar:
    st.divider(); st.write("Queue")
    if st.button("Refresh Q"): st.rerun()
    try:
        sh = load_data()
        q = pd.DataFrame(sh.worksheet("Queue").get_all_records())
        for i, r in q[q['Status']!='Done'].iterrows():
            if st.button(f"Pull {r['Name']}", key=f"q_{i}"):
                st.session_state.c_n = r['Name']; st.session_state.c_t = str(r['TaxID'])
                st.session_state.c_a1 = r['Address1']; st.session_state.c_a2 = r['Address2']; st.session_state.c_tel = str(r['Phone'])
                if r['Item']:
                     p = float(str(r['Price']).replace(',',''))
                     st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": p}]
                sh.worksheet("Queue").update_cell(i+2, 10, "Done")
                st.rerun()
    except: pass
