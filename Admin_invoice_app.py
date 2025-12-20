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
import time

# ==========================================
# ⚙️ 1. Config
# ==========================================
st.set_page_config(page_title="Nami Admin V106", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook ตรงนี้
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur" # ใส่ ID เผื่อไว้

try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except:
    FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. Auth & Connection (Hybrid Core)
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

# ฟังก์ชันอ่านข้อมูลแบบ Safe Mode (ป้องกัน Error ข้อมูลแหว่ง)
def load_data_safe():
    try:
        client = get_client()
        sh = client.open(SHEET_NAME)
        
        # 1. Config: อ่านแบบ Dict (Key:Value)
        ws_conf = sh.worksheet("Config")
        raw_conf = ws_conf.get_all_values()
        conf = {}
        for r in raw_conf:
            if len(r) >= 2: conf[str(r[0]).strip()] = str(r[1]).strip()
            
        # 2. Customers
        try: 
            cust_recs = sh.worksheet("Customers").get_all_records()
            cust_df = pd.DataFrame(cust_recs)
        except: cust_df = pd.DataFrame(columns=["Name"])
            
        # 3. Items
        try: 
            item_recs = sh.worksheet("Items").get_all_records()
            item_df = pd.DataFrame(item_recs)
        except: item_df = pd.DataFrame(columns=["ItemName"])
            
        # 4. Queue (Live)
        try: ws_q = sh.worksheet("Queue")
        except: ws_q = None
            
        return sh, conf, cust_df, item_df, ws_q
        
    except Exception as e:
        st.error(f"โหลดข้อมูลไม่สำเร็จ: {e}")
        return None, {}, pd.DataFrame(), pd.DataFrame(), None

# ==========================================
# 🖨️ 3. PDF Generator (Logo + Format V87)
# ==========================================
def generate_pdf_v106(doc_data, items, doc_type, running_no, date_str, vat_inc, logo_upload):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4; half_height = height / 2

    def wrap_text(text, width_limit, font, size):
        c.setFont(font, size); lines = []; words = str(text).split(' '); curr = []
        for w in words:
            if pdfmetrics.stringWidth(' '.join(curr + [w]), font, size) <= width_limit: curr.append(w)
            else:
                if curr: lines.append(' '.join(curr)); curr = [w]
                else: lines.append(w); curr = []
        if curr: lines.append(' '.join(curr))
        return lines

    def draw_content(y_base):
        margin = 15 * mm; top_y = y_base + half_height - margin
        
        # --- Logo ---
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                c.drawImage(img, margin, top_y - 10, width=25*mm, height=25*mm, preserveAspectRatio=True, mask='auto')
            except: pass

        # --- Shop Info ---
        box_x = width - margin - 260
        c.setFont(FONT_NAME, 14)
        c.drawString(box_x, top_y + 10, doc_data['shop_name'])
        c.setFont(FONT_NAME, 10)
        # Wrap Shop Address
        addr_lines = wrap_text(doc_data['shop_addr'], 250, FONT_NAME, 10)
        curr_y_shop = top_y - 5
        for l in addr_lines:
            c.drawString(box_x, curr_y_shop, l)
            curr_y_shop -= 10
        c.drawString(box_x, curr_y_shop, f"Tax ID: {doc_data['shop_tax']}")

        # --- Title ---
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        c.setFont(FONT_NAME, 18)
        c.drawCentredString(width/2, top_y - 25, f"ต้นฉบับ {title}")

        # --- Customer Info ---
        c.setFont(FONT_NAME, 12)
        info_y = top_y - 50
        c.drawString(margin, info_y, f"ลูกค้า: {doc_data['cust_name']}")
        c.drawString(margin, info_y - 15, f"Tax ID: {doc_data['cust_tax']}")
        c.drawString(margin, info_y - 30, f"โทร: {doc_data['cust_tel']}")
        
        # Address Wrap
        c.drawString(margin, info_y - 45, "ที่อยู่:")
        cust_addr_lines = wrap_text(doc_data['cust_addr'], 300, FONT_NAME, 12)
        ay = info_y - 45
        for l in cust_addr_lines:
            c.drawString(margin + 30, ay, l)
            ay -= 12

        # --- Doc Info (Right) ---
        c.drawRightString(width - margin, info_y, f"เลขที่: {running_no}")
        c.drawRightString(width - margin, info_y - 15, f"วันที่: {date_str}")

        # --- Table ---
        tbl_top = ay - 20
        c.line(margin, tbl_top, width-margin, tbl_top)
        c.drawString(margin, tbl_top - 15, "รายการสินค้า")
        c.drawRightString(width-margin, tbl_top - 15, "จำนวนเงิน")
        c.line(margin, tbl_top - 20, width-margin, tbl_top - 20)
        
        curr_y = tbl_top - 35
        total = 0
        for item in items:
            name = item['name']; qty = item['qty']; price = item['price']
            amount = qty * price; total += amount
            c.drawString(margin, curr_y, f"{name} ({qty:,.0f} x {price:,.2f})")
            c.drawRightString(width-margin, curr_y, f"{amount:,.2f}")
            curr_y -= 15
        
        c.line(margin, curr_y, width-margin, curr_y)
        
        # VAT Logic
        if vat_inc:
            grand = total
            pre_vat = total * 100 / 107
            vat = total - pre_vat
        else:
            pre_vat = total
            vat = total * 0.07
            grand = total + vat

        c.setFont(FONT_NAME, 12)
        c.drawRightString(width-margin, curr_y - 20, f"รวมสุทธิ: {grand:,.2f}")
        c.setFont(FONT_NAME, 10)
        c.drawRightString(width-margin, curr_y - 35, f"(สินค้า {pre_vat:,.2f} + VAT {vat:,.2f})")

    if doc_type == "ABB": draw_content(half_height)
    else: 
        draw_content(half_height)
        c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0)
        draw_content(0)
    
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 4. State & Login
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
# ตัวแปรฟอร์ม
for k in ['f_n','f_t','f_a','f_tel', 's_n','s_t','s_a']:
    if k not in st.session_state: st.session_state[k] = ""

# --- Sidebar Login/Logout ---
with st.sidebar:
    if st.session_state.logged_in:
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.rerun()
    else:
        st.header("Login")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else: st.error("ผิดครับ")
        st.stop() # หยุดการทำงานถ้ายังไม่ Login

# โหลดข้อมูล (หลังจาก Login ผ่านแล้ว)
sh, conf, cust_df, item_df, ws_q = load_data_safe()

# Sync ข้อมูลร้านเข้า State ครั้งแรก
if not st.session_state.s_n and conf:
    st.session_state.s_n = conf.get("ShopName", "")
    st.session_state.s_t = conf.get("TaxID", "")
    st.session_state.s_a = conf.get("Address", "")

# ==========================================
# 🖥️ 5. UI Layout
# ==========================================
st.title("🧾 Nami Invoice (V106 Hybrid Master)")

# --- 1. ข้อมูลผู้ขาย (Editable + Save + Logo) ---
with st.expander("🏠 ข้อมูลร้านค้า & โลโก้ (แก้ไขได้)", expanded=True):
    col_s1, col_s2 = st.columns([2, 1])
    with col_s1:
        st.session_state.s_n = st.text_input("ชื่อร้าน", st.session_state.s_n)
        st.session_state.s_t = st.text_input("Tax ID", st.session_state.s_t)
        st.session_state.s_a = st.text_area("ที่อยู่ (ใส่ \\n เพื่อขึ้นบรรทัดใหม่)", st.session_state.s_a, height=100)
        
        if st.button("💾 บันทึกข้อมูลร้านลง Cloud"):
            try:
                # ใช้วิธีค้นหา Cell แบบบ้านๆ แต่มั่นคง
                ws_c = sh.worksheet("Config")
                cells = ws_c.findall("ShopName")
                if cells: ws_c.update_cell(cells[0].row, 2, st.session_state.s_n)
                
                cells = ws_c.findall("TaxID")
                if cells: ws_c.update_cell(cells[0].row, 2, st.session_state.s_t)
                
                cells = ws_c.findall("Address")
                if cells: ws_c.update_cell(cells[0].row, 2, st.session_state.s_a)
                
                st.success("บันทึกข้อมูลร้านเรียบร้อย!")
            except Exception as e:
                st.error(f"บันทึกไม่ได้: {e}")

    with col_s2:
        st.write("🖼️ **โลโก้ร้าน**")
        uploaded_logo = st.file_uploader("เลือกไฟล์ภาพ", type=['png', 'jpg', 'jpeg'])
        if uploaded_logo: st.image(uploaded_logo, width=100)

# --- 2. ข้อมูลลูกค้า & เอกสาร ---
col_main, col_cart = st.columns([1.5, 1])

with col_main:
    st.subheader("👤 ข้อมูลลูกค้า")
    # Search (ถ้า DataFrame ว่าง ให้ใส่ list ว่างๆ ไว้ก่อน กัน Error)
    cust_options = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else [""]
    sel_cust = st.selectbox("🔍 ค้นหาลูกค้าเก่า", cust_options)
    
    if sel_cust and sel_cust != st.session_state.get('last_c'):
        r = cust_df[cust_df['Name'] == sel_cust].iloc[0]
        st.session_state.f_n = r['Name']
        st.session_state.f_t = str(r['TaxID'])
        st.session_state.f_a = f"{r['Address1']} {r['Address2']}"
        st.session_state.f_tel = str(r['Phone'])
        st.session_state.last_c = sel_cust
        st.rerun()

    c1, c2 = st.columns(2)
    st.session_state.f_n = c1.text_input("ชื่อลูกค้า", st.session_state.f_n)
    st.session_state.f_t = c2.text_input("Tax ID (ลูกค้า)", st.session_state.f_t)
    st.session_state.f_a = st.text_area("ที่อยู่ลูกค้า", st.session_state.f_a, height=68)
    st.session_state.f_tel = st.text_input("เบอร์โทร", st.session_state.f_tel)
    
    # ปุ่มล้าง/จำค่า
    b_clr, b_save = st.columns(2)
    if b_clr.button("🧹 ล้างค่า"):
        st.session_state.f_n = ""; st.session_state.f_t = ""; st.session_state.f_a = ""; st.session_state.f_tel = ""
        st.rerun()
    if b_save.button("💾 จำค่าลูกค้า"):
        try:
            sh.worksheet("Customers").append_row([st.session_state.f_n, st.session_state.f_t, st.session_state.f_a, "", st.session_state.f_tel])
            st.toast("บันทึกลูกค้าใหม่แล้ว")
        except: st.error("บันทึกไม่ผ่าน")

    st.divider()
    st.subheader("📄 ตั้งค่าเอกสาร")
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    # ดึงเลขล่าสุดมาโชว์
    curr_run = conf.get(run_key, "INV-000")
    run_no = st.text_input("เลขที่เอกสาร (แก้ไขได้)", value=curr_run)
    doc_date = st.date_input("วันที่", datetime.now())
    vat_inc = st.checkbox("ราคารวม VAT แล้ว", value=True)

# --- 3. ตะกร้าสินค้า ---
with col_cart:
    st.subheader("🛒 รายการสินค้า")
    item_opts = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else [""]
    sel_item = st.selectbox("สินค้า", item_opts)
    
    col_q, col_p = st.columns(2)
    qty = col_q.number_input("จำนวน", 1, 100, 1)
    price = col_p.number_input("ราคา", 0.0, step=10.0)
    
    if st.button("➕ เพิ่มรายการ"):
        if sel_item:
            st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        df_cart = pd.DataFrame(st.session_state.cart)
        df_cart['Total'] = df_cart['qty'] * df_cart['price']
        st.dataframe(df_cart, use_container_width=True, hide_index=True)
        
        grand_total = df_cart['Total'].sum()
        st.markdown(f"### 💰 รวม: {grand_total:,.2f}")
        
        if st.button("❌ ลบรายการล่าสุด"):
            st.session_state.cart.pop()
            st.rerun()
            
        st.markdown("---")
        
        # 🟢 FINAL BUTTON
        if st.button("🖨️ ออกใบกำกับภาษี & Save", type="primary", use_container_width=True):
            if not st.session_state.f_n:
                st.error("ใส่ชื่อลูกค้าก่อนครับ")
            else:
                with st.spinner("กำลังทำงาน..."):
                    # 1. Save SalesLog (Date, Amount)
                    try:
                        sh.worksheet("SalesLog").append_row([str(doc_date), grand_total])
                    except: st.warning("บันทึกยอดขายไม่ได้ (แต่จะออก PDF ให้)")

                    # 2. Update Running No
                    try:
                        # Auto Increment Logic
                        p = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                        if p:
                            nxt = f"{p.group(1)}{str(int(p.group(2))+1).zfill(len(p.group(2)))}"
                            ws_conf = sh.worksheet("Config")
                            # หา cell ที่ key ตรงกัน
                            cell = ws_conf.find(run_key)
                            ws_conf.update_cell(cell.row, 2, nxt)
                    except: pass

                    # 3. Generate PDF
                    d_data = {
                        "shop_name": st.session_state.s_n, "shop_tax": st.session_state.s_t, "shop_addr": st.session_state.s_a,
                        "cust_name": st.session_state.f_n, "cust_tax": st.session_state.f_t, "cust_addr": st.session_state.f_a, "cust_tel": st.session_state.f_tel
                    }
                    pdf = generate_pdf_v106(d_data, st.session_state.cart, doc_type, run_no, str(doc_date), vat_inc, uploaded_logo)
                    fname = f"INV_{run_no}.pdf"
                    
                    # 4. Upload via Webhook
                    try:
                        payload = {"filename": fname, "mimeType": "application/pdf", "file": base64.b64encode(pdf.getvalue()).decode('utf-8'), "folderId": DRIVE_FOLDER_ID}
                        requests.post(APPS_SCRIPT_URL, json=payload)
                        st.success("✅ Backup ลง Drive เรียบร้อย")
                    except: st.error("⚠️ Backup ไม่ผ่าน (แต่โหลดไฟล์ได้)")
                    
                    # 5. Download Link
                    st.download_button("⬇️ Download PDF", pdf, fname, "application/pdf")
                    
                    # Clear Cart
                    st.session_state.cart = []

# --- Sidebar Queue (Hybrid) ---
with st.sidebar:
    st.divider()
    st.subheader("☁️ Queue Online")
    if st.button("🔄 Refresh Queue"): st.rerun()
    
    if ws_q:
        try:
            q_recs = ws_q.get_all_records()
            q_df = pd.DataFrame(q_recs)
            pending = q_df[q_df['Status'] != 'Done']
            for i, r in pending.iterrows():
                st.info(f"{r['Name']} ({r['Price']})")
                if st.button("ดึง", key=f"q_{i}"):
                    st.session_state.f_n = r['Name']
                    st.session_state.f_t = str(r['TaxID'])
                    st.session_state.f_a = f"{r['Address1']} {r['Address2']}"
                    st.session_state.f_tel = str(r['Phone'])
                    # Auto add item
                    if r['Item']:
                        try: p = float(str(r['Price']).replace(',',''))
                        except: p = 0.0
                        st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": p}]
                    
                    # Mark Done immediately
                    ws_q.update_cell(i+2, 10, "Done")
                    st.rerun()
        except: st.caption("No Queue / Connect Error")

