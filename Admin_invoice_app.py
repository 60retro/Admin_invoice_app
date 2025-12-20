import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
from io import BytesIO
import requests
import base64
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import re

# ==========================================
# ⚙️ 1. Config & Setup
# ==========================================
st.set_page_config(page_title="Nami Web (V87 Clone)", layout="wide", page_icon="🧾")

# 🟢 CONFIGURATION
ADMIN_PASSWORD = "1234"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL เดิมของคุณ
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# Load Font
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except:
    FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. Google Services
# ==========================================
@st.cache_resource
def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        return ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else: return ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

def get_client(): return gspread.authorize(get_credentials())

# ==========================================
# 🛠️ 3. Helper Functions
# ==========================================
def smart_clean_address(addr1, addr2):
    # (Logic เดิมของ V87 Desktop)
    return addr1, "", addr2 # Simplified for mapping

def upload_via_script(pdf_buffer, filename):
    try:
        pdf_buffer.seek(0)
        payload = {
            "filename": filename, 
            "mimeType": "application/pdf", 
            "file": base64.b64encode(pdf_buffer.read()).decode('utf-8'),
            "folderId": DRIVE_FOLDER_ID
        }
        resp = requests.post(APPS_SCRIPT_URL, json=payload)
        return resp.json().get("status") == "success"
    except: return False

# ==========================================
# 🖨️ 4. PDF Generation (V87 Logic เป๊ะๆ)
# ==========================================
def generate_pdf_v87(doc_data, items, doc_type, running_no, date_str, vat_included):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4; half_height = height / 2

    def wrap_text(text, width_limit, font, size):
        c.setFont(font, size); lines = []; words = str(text).split(' '); curr = []
        for w in words:
            if pdfmetrics.stringWidth(' '.join(curr + [w]), font, size) <= width_limit: curr.append(w)
            else: lines.append(' '.join(curr)); curr = [w]
        if curr: lines.append(' '.join(curr))
        return lines

    def draw_content(y_base):
        margin = 15 * mm; top_y = y_base + half_height - margin
        
        # Shop Info
        c.setFont(FONT_NAME, 12)
        c.drawString(width - margin - 260, top_y + 10, doc_data['shop_name'])
        c.setFont(FONT_NAME, 10)
        addr_lines = wrap_text(doc_data['shop_addr'], 250, FONT_NAME, 10)
        curr_y = top_y - 5
        for l in addr_lines: c.drawString(width - margin - 260, curr_y, l); curr_y -= 10
        
        # Title
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        c.setFont(FONT_NAME, 16)
        c.drawCentredString(width/2, top_y - 20, f"ต้นฉบับ {title}")
        
        # Header Info
        c.setFont(FONT_NAME, 12)
        c.drawString(margin, top_y - 40, f"ลูกค้า: {doc_data['cust_name']}")
        c.drawString(margin, top_y - 55, f"Tax ID: {doc_data['cust_tax']}")
        c.drawString(margin, top_y - 70, f"ที่อยู่: {doc_data['cust_addr']}")
        
        c.drawRightString(width - margin, top_y - 40, f"เลขที่: {running_no}")
        c.drawRightString(width - margin, top_y - 55, f"วันที่: {date_str}")

        # Table
        tbl_top = top_y - 90
        c.line(margin, tbl_top, width-margin, tbl_top)
        c.drawString(margin, tbl_top - 15, "รายการ")
        c.drawRightString(width-margin, tbl_top - 15, "จำนวนเงิน")
        c.line(margin, tbl_top - 20, width-margin, tbl_top - 20)
        
        curr_y = tbl_top - 35
        total = 0
        for item in items:
            name = item['name']; qty = item['qty']; price = item['price']
            amount = qty * price; total += amount
            c.drawString(margin, curr_y, f"{name} ({qty:.0f} x {price:.2f})")
            c.drawRightString(width-margin, curr_y, f"{amount:,.2f}")
            curr_y -= 15
        
        c.line(margin, curr_y, width-margin, curr_y)
        
        # VAT Logic
        if vat_included:
            grand_total = total
            before_vat = total * 100 / 107
            vat_amt = total - before_vat
        else:
            before_vat = total
            vat_amt = total * 0.07
            grand_total = total + vat_amt

        c.drawRightString(width-margin, curr_y - 20, f"รวมเงิน: {grand_total:,.2f}")
        c.setFont(FONT_NAME, 10)
        c.drawRightString(width-margin, curr_y - 35, f"(ราคาสินค้า {before_vat:,.2f} + VAT {vat_amt:,.2f})")

    if doc_type == "ABB": draw_content(half_height)
    else: draw_content(half_height); c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0); draw_content(0)
    
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 5. Session State Init
# ==========================================
if 'init' not in st.session_state:
    st.session_state.init = True
    st.session_state.cart = []
    # Shop Defaults
    st.session_state.s_name = "ร้านนามิ"; st.session_state.s_tax = ""; st.session_state.s_addr = ""
    # Customer Defaults
    st.session_state.c_name = ""; st.session_state.c_tax = ""; st.session_state.c_addr1 = ""; st.session_state.c_addr2 = ""; st.session_state.c_tel = ""
    # Doc Defaults
    st.session_state.doc_no = "INV-000"; st.session_state.doc_date = datetime.now().date()
    st.session_state.vat_inc = True

# ==========================================
# 🔄 6. Sync Function (หัวใจหลัก)
# ==========================================
def sync_data():
    try:
        client = get_client(); sh = client.open(SHEET_NAME)
        
        # 1. Pull Config
        conf = dict(sh.worksheet("Config").get_all_values())
        st.session_state.s_name = conf.get("ShopName", "")
        st.session_state.s_tax = conf.get("TaxID", "")
        st.session_state.s_addr = conf.get("Address", "")
        # Update Doc No based on selection
        # (จะอัปเดตตอนกดปุ่มสร้าง PDF)
        
        # 2. Pull Items & Customers
        st.session_state.db_items = pd.DataFrame(sh.worksheet("Items").get_all_records())
        st.session_state.db_custs = pd.DataFrame(sh.worksheet("Customers").get_all_records())
        
        st.toast("✅ Sync ข้อมูลล่าสุดเรียบร้อย!", icon="☁️")
    except Exception as e: st.error(f"Sync Failed: {e}")

# Load Data on Start
if 'db_items' not in st.session_state: sync_data()

# ==========================================
# 🖥️ 7. UI Layout (V87 Clone)
# ==========================================
st.markdown("### 🧾 Nami Invoice Manager (V87 Web Clone)")

# --- Top Bar: Sync ---
col_sync, col_space = st.columns([1, 5])
with col_sync:
    if st.button("🔄 Sync DB", type="secondary", use_container_width=True): sync_data()

# --- Section 1: ข้อมูลผู้ขาย (Seller) ---
with st.expander("🔒 ข้อมูลผู้ขาย (Admin)", expanded=False):
    c1, c2 = st.columns(2)
    with c1: 
        st.session_state.s_name = st.text_input("ชื่อร้าน", st.session_state.s_name)
        st.session_state.s_tax = st.text_input("Tax ID", st.session_state.s_tax)
    with c2:
        st.session_state.s_addr = st.text_area("ที่อยู่ร้าน", st.session_state.s_addr, height=100)
    if st.button("บันทึกข้อมูลร้าน"):
        # Logic to save back to Sheet
        try:
            client = get_client(); ws = client.open(SHEET_NAME).worksheet("Config")
            ws.update_cell(ws.find("ShopName").row, 2, st.session_state.s_name)
            ws.update_cell(ws.find("TaxID").row, 2, st.session_state.s_tax)
            ws.update_cell(ws.find("Address").row, 2, st.session_state.s_addr)
            st.success("บันทึกแล้ว")
        except: st.error("บันทึกไม่ได้")

st.divider()

# --- Section 2: ข้อมูลลูกค้า (Customer) ---
c_left, c_right = st.columns([2, 1])

with c_left:
    st.subheader("👤 ข้อมูลลูกค้า")
    # Search Box
    cust_names = [""] + list(st.session_state.db_custs['Name'].unique()) if not st.session_state.db_custs.empty else []
    sel_cust = st.selectbox("🔍 ค้นหาลูกค้าเก่า", cust_names)
    
    # Auto-fill Logic
    if sel_cust and sel_cust != st.session_state.get('prev_cust'):
        r = st.session_state.db_custs[st.session_state.db_custs['Name'] == sel_cust].iloc[0]
        st.session_state.c_name = r['Name']; st.session_state.c_tax = str(r['TaxID'])
        st.session_state.c_addr1 = r['Address1']; st.session_state.c_addr2 = r['Address2']; st.session_state.c_tel = str(r['Phone'])
        st.session_state.prev_cust = sel_cust
        st.rerun()

    # Form Inputs
    cc1, cc2 = st.columns(2)
    st.session_state.c_name = cc1.text_input("ชื่อลูกค้า", st.session_state.c_name)
    st.session_state.c_tax = cc2.text_input("Tax ID (ลูกค้า)", st.session_state.c_tax)
    st.session_state.c_addr1 = st.text_input("ที่อยู่ 1", st.session_state.c_addr1)
    st.session_state.c_addr2 = st.text_input("ที่อยู่ 2", st.session_state.c_addr2)
    st.session_state.c_tel = st.text_input("เบอร์โทร", st.session_state.c_tel)

    # Action Buttons (Clear / Save)
    b1, b2, b3 = st.columns([1, 1, 3])
    if b1.button("🧹 ล้างค่า"):
        st.session_state.c_name = ""; st.session_state.c_tax = ""; st.session_state.c_addr1 = ""; st.session_state.c_addr2 = ""; st.session_state.c_tel = ""
        st.rerun()
    
    if b2.button("💾 จำค่า"):
        # Save new customer to Sheet
        try:
            client = get_client(); ws = client.open(SHEET_NAME).worksheet("Customers")
            ws.append_row([st.session_state.c_name, st.session_state.c_tax, st.session_state.c_addr1, st.session_state.c_addr2, st.session_state.c_tel])
            st.toast("บันทึกลูกค้าใหม่แล้ว")
            sync_data() # Refresh data
        except: st.error("บันทึกไม่สำเร็จ")

# --- Section 3: เอกสาร (Document) ---
with c_right:
    st.subheader("📄 ตั้งค่าเอกสาร")
    st.session_state.doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    
    # Running No Logic (Get from Config)
    # (Simplified: Just verify with sheet on load)
    
    st.session_state.doc_no = st.text_input("เลขที่เอกสาร", st.session_state.doc_no)
    st.session_state.doc_date = st.date_input("วันที่", st.session_state.doc_date)

st.divider()

# --- Section 4: สินค้า (Items) ---
st.subheader("🛒 รายการสินค้า")
i1, i2, i3, i4 = st.columns([3, 1, 1, 1])

item_names = [""] + list(st.session_state.db_items['ItemName'].unique()) if not st.session_state.db_items.empty else []
sel_item = i1.selectbox("เลือกสินค้า", item_names)
qty = i2.number_input("จำนวน", 1, value=1)
price = i3.number_input("ราคา", 0.0, value=0.0)

if i4.button("➕ เพิ่ม") and sel_item:
    st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})

# Cart Table
if st.session_state.cart:
    df_cart = pd.DataFrame(st.session_state.cart)
    df_cart['Total'] = df_cart['qty'] * df_cart['price']
    st.dataframe(df_cart, use_container_width=True)
    
    col_sum, col_act = st.columns([3, 1])
    grand_total = df_cart['Total'].sum()
    col_sum.markdown(f"### 💰 ยอดรวม: `{grand_total:,.2f}` บาท")
    
    if col_act.button("ลบรายการล่าสุด"): 
        st.session_state.cart.pop(); st.rerun()

# --- Section 5: Footer Actions ---
st.divider()
f1, f2, f3 = st.columns([1, 2, 2])

st.session_state.vat_inc = f1.checkbox("ราคารวม VAT แล้ว", value=True)
use_backup = f2.checkbox("Backup to Drive", value=True)

if f3.button("🖨️ พิมพ์ PDF (Generate)", type="primary", use_container_width=True):
    if not st.session_state.c_name: st.error("ระบุชื่อลูกค้าก่อน")
    else:
        with st.spinner("Processing..."):
            # 1. Update Sheet
            try:
                client = get_client(); sh = client.open(SHEET_NAME)
                # Update Running No
                ws_conf = sh.worksheet("Config")
                # Auto Increment Logic
                prefix_match = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", st.session_state.doc_no)
                if prefix_match:
                    p, n = prefix_match.groups()
                    next_run = f"{p}{str(int(n)+1).zfill(len(n))}"
                    run_key = "Full_No" if st.session_state.doc_type == "Full" else "Abb_No"
                    cell = ws_conf.find(run_key)
                    ws_conf.update_cell(cell.row, 2, next_run)
                
                # Update Sales Log
                try: sh.worksheet("SalesLog").append_row([str(st.session_state.doc_date), st.session_state.doc_no, st.session_state.c_name, grand_total, "Web"])
                except: pass
            except: pass

            # 2. Generate PDF
            info = {
                "shop_name": st.session_state.s_name, "shop_addr": st.session_state.s_addr, "shop_tax": st.session_state.s_tax,
                "cust_name": st.session_state.c_name, "cust_tax": st.session_state.c_tax, 
                "cust_addr": f"{st.session_state.c_addr1} {st.session_state.c_addr2}".strip(), "cust_tel": st.session_state.c_tel
            }
            pdf = generate_pdf_v87(info, st.session_state.cart, st.session_state.doc_type, st.session_state.doc_no, str(st.session_state.doc_date), st.session_state.vat_inc)
            
            # 3. Backup
            fname = f"INV_{st.session_state.doc_no}.pdf"
            if use_backup: upload_via_script(pdf, fname)
            
            # 4. Download
            st.success("เสร็จสิ้น!")
            st.download_button("⬇️ Download PDF", pdf, fname, "application/pdf")
            
            # 5. Refresh Sync
            sync_data()
