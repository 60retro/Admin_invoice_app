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
st.set_page_config(page_title="Nami Admin V107", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "1234"
# 🟢 ใส่ URL Webhook (Apps Script) ของคุณ
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec"
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# Load Font (พยายามโหลดฟอนต์ไทย)
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
    FONT_SIZE_STD = 12
    FONT_SIZE_BOLD = 14
except:
    FONT_NAME = 'Helvetica'
    FONT_SIZE_STD = 10
    FONT_SIZE_BOLD = 12

# ==========================================
# 🔌 2. Google Services (Hybrid Core)
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

# Cache ข้อมูลสินค้า/ลูกค้า (5 นาที) เพื่อความเร็วและลด Quota
@st.cache_data(ttl=300)
def load_db_cache():
    try:
        client = get_client(); sh = client.open(SHEET_NAME)
        # Items
        try: items = pd.DataFrame(sh.worksheet("Items").get_all_records())
        except: items = pd.DataFrame(columns=["ItemName"])
        # Customers
        try: custs = pd.DataFrame(sh.worksheet("Customers").get_all_records())
        except: custs = pd.DataFrame(columns=["Name"])
        return items, custs
    except: return pd.DataFrame(), pd.DataFrame()

def upload_via_webhook(pdf_bytes, filename):
    try:
        payload = {
            "filename": filename,
            "mimeType": "application/pdf",
            "file": base64.b64encode(pdf_bytes).decode('utf-8'),
            "folderId": DRIVE_FOLDER_ID
        }
        resp = requests.post(APPS_SCRIPT_URL, json=payload)
        return resp.json().get("status") == "success"
    except: return False

# ==========================================
# 🖨️ 3. PDF Generator (V87 Desktop Logic - Exact Replica)
# ==========================================
def generate_pdf_v107(doc_data, items, doc_type, running_no, date_str, vat_inc, logo_upload):
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
        margin = 15 * mm
        top_y = y_base + half_height - margin
        page_w = width - (2 * margin)
        
        # --- 1. Header & Logo ---
        logo_h = 20 * mm
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                # วาดโลโก้ (ซ้ายบน)
                c.drawImage(img, margin, top_y - 10, width=30*mm, height=logo_h, preserveAspectRatio=True, mask='auto')
            except: pass

        # --- 2. Shop Box (กรอบสี่เหลี่ยมมน ขวาบน) ---
        box_w = 90 * mm
        box_h = 25 * mm
        box_x = width - margin - box_w
        box_y = top_y - 5
        
        c.setLineWidth(1)
        c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0) # กรอบมน
        
        # Shop Name
        c.setFont(FONT_NAME, FONT_SIZE_BOLD)
        c.drawString(box_x + 3*mm, box_y + box_h - 6*mm, doc_data['shop_name'])
        
        # Shop Address (Wrap)
        c.setFont(FONT_NAME, FONT_SIZE_STD - 2)
        addr_lines = wrap_text(doc_data['shop_addr'], box_w - 6*mm, FONT_NAME, FONT_SIZE_STD - 2)
        curr_y_addr = box_y + box_h - 11*mm
        for l in addr_lines:
            c.drawString(box_x + 3*mm, curr_y_addr, l)
            curr_y_addr -= 4*mm
        # c.drawString(box_x + 3*mm, curr_y_addr, f"โทร: {doc_data.get('shop_tel','')}")

        # --- 3. Title ---
        title_txt = "ต้นฉบับ ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        c.setFont(FONT_NAME, FONT_SIZE_BOLD + 4)
        c.drawCentredString(width/2, top_y - 25*mm, title_txt)
        
        # --- 4. Info Bar (TaxID & No) ---
        bar_y = top_y - 35*mm
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        c.drawString(margin, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['shop_tax']}")
        c.drawRightString(width - margin, bar_y, f"เลขที่ : {running_no}")

        # --- 5. Customer & Doc Info Box (กรอบใหญ่แบ่งครึ่ง) ---
        info_box_y = bar_y - 2*mm
        info_box_h = 28 * mm
        info_box_btm = info_box_y - info_box_h
        
        c.rect(margin, info_box_btm, page_w, info_box_h) # กรอบใหญ่
        div_x = width - margin - 70*mm # เส้นแบ่งแนวตั้ง
        c.line(div_x, info_box_y, div_x, info_box_btm)
        
        # >> Left Side (Customer)
        cx = margin + 2*mm
        cy = info_box_y - 5*mm
        c.drawString(cx, cy, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['cust_tax']}")
        cy -= 5*mm
        c.drawString(cx, cy, f"ชื่อลูกค้า : {doc_data['cust_name']}")
        cy -= 5*mm
        c.drawString(cx, cy, f"ที่อยู่ :")
        # Wrap Customer Addr
        cust_addr_lines = wrap_text(doc_data['cust_addr'], (div_x - cx) - 5*mm, FONT_NAME, FONT_SIZE_STD)
        ay = cy
        for l in cust_addr_lines[:2]: # Limit 2 lines
            c.drawString(cx + 10*mm, ay, l)
            ay -= 5*mm
        c.drawString(cx, info_box_btm + 2*mm, f"โทรศัพท์ : {doc_data['cust_tel']}")

        # >> Right Side (Doc Details)
        dx = div_x + 3*mm
        dy = info_box_y - 5*mm
        c.drawString(dx, dy, f"วันที่เอกสาร : {date_str}")
        c.drawString(dx, dy - 5*mm, "พนักงานขาย : -")
        c.drawString(dx, dy - 10*mm, "เงื่อนไขการชำระ : สด")

        # --- 6. Items Table ---
        tbl_top = info_box_btm - 2*mm
        tbl_header_h = 8*mm
        
        # Header Box
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(margin, tbl_top - tbl_header_h, page_w, tbl_header_h, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        
        # Columns: No, Item, Qty, Price, Total
        cols = [10*mm, 90*mm, 20*mm, 30*mm, 30*mm]
        col_x = [margin]
        for w_col in cols: col_x.append(col_x[-1] + w_col)
        
        # Header Text
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]
        c.setFont(FONT_NAME, FONT_SIZE_BOLD)
        for i, h in enumerate(headers):
            c.drawCentredString(col_x[i] + cols[i]/2, tbl_top - 6*mm, h)
            
        # Items Content
        curr_y = tbl_top - tbl_header_h
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        total = 0
        
        for idx, item in enumerate(items, 1):
            if idx > 12: break # Limit items per page
            nm = item['name']; qty = item['qty']; price = item['price']
            amt = qty * price; total += amt
            
            row_h = 8*mm
            text_y = curr_y - 6*mm
            
            # Draw Cells
            c.drawCentredString(col_x[0] + cols[0]/2, text_y, str(idx))
            c.drawString(col_x[1] + 2*mm, text_y, str(nm))
            c.drawRightString(col_x[2] + cols[2] - 2*mm, text_y, f"{qty:,.0f}")
            c.drawRightString(col_x[3] + cols[3] - 2*mm, text_y, f"{price:,.2f}")
            c.drawRightString(col_x[4] + cols[4] - 2*mm, text_y, f"{amt:,.2f}")
            
            # Vertical Lines
            for x in col_x: c.line(x, curr_y, x, curr_y - row_h)
            c.line(col_x[-1], curr_y, col_x[-1], curr_y - row_h) # Last line
            
            curr_y -= row_h
            
        # Close Table Box
        c.line(margin, curr_y, width-margin, curr_y) # Bottom line
        
        # Fill Empty Rows (ลากเส้นยาวลงมาถึง Footer แบบ V87)
        btm_y = top_y - 140*mm
        if curr_y > btm_y:
            c.rect(margin, btm_y, page_w, curr_y - btm_y) # Empty box
            for x in col_x[1:-1]: # Vertical lines for empty space
                c.line(x, curr_y, x, btm_y)
            curr_y = btm_y

        # --- 7. Footer (Totals) ---
        # VAT Logic
        if vat_inc:
            grand = total; pre_vat = total * 100 / 107; vat = total - pre_vat
        else:
            pre_vat = total; vat = total * 0.07; grand = total + vat
            
        ft_h = 7*mm
        labels = ["รวมเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        values = [f"{total:,.2f}", "-", f"{pre_vat:,.2f}", f"{vat:,.2f}", f"{grand:,.2f}"]
        
        # Draw Footer Rows
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        for i in range(5):
            c.rect(col_x[3], curr_y - ft_h, cols[3], ft_h) # Label Box
            c.rect(col_x[4], curr_y - ft_h, cols[4], ft_h) # Value Box
            
            c.drawRightString(col_x[4] - 2*mm, curr_y - 5*mm, labels[i])
            c.drawRightString(col_x[5] - 2*mm, curr_y - 5*mm, values[i])
            curr_y -= ft_h

        # Signatures
        sig_y = curr_y - 15*mm
        c.drawString(margin + 10*mm, sig_y, "ผู้รับสินค้า ...........................................................")
        c.drawString(width - margin - 60*mm, sig_y, "ผู้รับเงิน ...........................................................")

    if doc_type == "ABB": draw_content(half_height)
    else: 
        draw_content(half_height)
        c.setDash(3, 3); c.line(5*mm, half_height, width-5*mm, half_height); c.setDash(1, 0)
        draw_content(0)
    
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 4. State & Logic
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['f_n','f_t','f_a','f_tel', 's_n','s_t','s_a']:
    if k not in st.session_state: st.session_state[k] = ""

# --- Sidebar: Sync & Login ---
with st.sidebar:
    st.title("Admin Menu")
    
    # 🟢 Sync Button (The God Button)
    if st.button("🔄 Sync DB (โหลดข้อมูลใหม่)", type="primary"):
        st.cache_data.clear() # ล้าง Cache
        st.rerun() # รีโหลดหน้า
    
    st.divider()
    
    if not st.session_state.logged_in:
        pwd = st.text_input("รหัสผ่าน", type="password")
        if st.button("เข้าสู่ระบบ"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else: st.error("รหัสผ่านผิด")
    else:
        st.success("✅ เข้าสู่ระบบแล้ว")
        if st.button("ออกจากระบบ"):
            st.session_state.logged_in = False
            st.rerun()

# Stop if not logged in
if not st.session_state.logged_in: st.stop()

# Load Data (After Login)
item_df, cust_df = load_db_cache()

# Load Config (Real-time)
try:
    client = get_client(); sh = client.open(SHEET_NAME)
    ws_conf = sh.worksheet("Config")
    conf_list = ws_conf.get_all_values()
    conf = {str(r[0]): str(r[1]) for r in conf_list if len(r)>=2}
    
    # Init Shop Info (ถ้ายังไม่มีใน State)
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName","")
        st.session_state.s_t = conf.get("TaxID","")
        st.session_state.s_a = conf.get("Address","")
except:
    st.error("เชื่อมต่อ Database ไม่ได้ (ลองกด Sync DB)")
    st.stop()

# ==========================================
# 🖥️ 5. UI Layout
# ==========================================
st.title("🧾 Nami Invoice (V107 Clone)")

col_L, col_R = st.columns([1.2, 1])

with col_L:
    # --- 1. Shop Info & Logo ---
    with st.expander("🏠 ข้อมูลร้าน & โลโก้", expanded=True):
        c1, c2 = st.columns(2)
        st.session_state.s_n = c1.text_input("ชื่อร้าน", st.session_state.s_n)
        st.session_state.s_t = c2.text_input("Tax ID", st.session_state.s_t)
        st.session_state.s_a = st.text_area("ที่อยู่ (ใส่ \\n เพื่อขึ้นบรรทัดใหม่)", st.session_state.s_a, height=80)
        
        logo_up = st.file_uploader("โลโก้ (PNG/JPG)", type=['png','jpg','jpeg'])
        
        if st.button("บันทึกข้อมูลร้าน"):
            try:
                # Update by finding cells
                cell = ws_conf.find("ShopName"); ws_conf.update_cell(cell.row, 2, st.session_state.s_n)
                cell = ws_conf.find("TaxID"); ws_conf.update_cell(cell.row, 2, st.session_state.s_t)
                cell = ws_conf.find("Address"); ws_conf.update_cell(cell.row, 2, st.session_state.s_a)
                st.success("บันทึกแล้ว!")
            except: st.error("บันทึกไม่สำเร็จ")

    # --- 2. Customer Info ---
    st.subheader("👤 ข้อมูลลูกค้า")
    cust_opts = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else [""]
    sel_cust = st.selectbox("🔍 ค้นหาลูกค้า", cust_opts)
    
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
    
    if st.button("🧹 ล้างค่า"):
        for k in ['f_n','f_t','f_a','f_tel']: st.session_state[k] = ""
        st.rerun()

    st.divider()
    
    # --- 3. Document Settings ---
    st.subheader("📄 ตั้งค่าเอกสาร")
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    curr_run = conf.get(run_key, "INV-000")
    
    col_d1, col_d2 = st.columns(2)
    run_no = col_d1.text_input("เลขที่เอกสาร", value=curr_run)
    doc_date = col_d2.date_input("วันที่", datetime.now())
    vat_inc = st.checkbox("ราคารวม VAT แล้ว", value=True)

with col_R:
    # --- 4. Cart ---
    st.subheader("🛒 รายการสินค้า")
    item_opts = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else [""]
    sel_item = st.selectbox("สินค้า", item_opts)
    
    c1, c2, c3 = st.columns([1, 1, 1])
    qty = c1.number_input("จำนวน", 1, value=1)
    price = c2.number_input("ราคา", 0.0)
    if c3.button("➕ เพิ่ม"):
        if sel_item: st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        df_cart = pd.DataFrame(st.session_state.cart)
        df_cart['Total'] = df_cart['qty'] * df_cart['price']
        st.dataframe(df_cart, use_container_width=True, hide_index=True)
        
        grand_total = df_cart['Total'].sum()
        st.info(f"💰 ยอดรวม: {grand_total:,.2f} บาท")
        
        if st.button("❌ ลบรายการล่าสุด"):
            st.session_state.cart.pop(); st.rerun()
            
        st.divider()
        use_backup = st.checkbox("Backup ลง Drive", value=True)
        
        if st.button("🖨️ ออกใบกำกับภาษี (Generate)", type="primary", use_container_width=True):
            if not st.session_state.f_n: st.error("ใส่ชื่อลูกค้าก่อนครับ"); st.stop()
            
            with st.spinner("Processing..."):
                # 1. Save SalesLog
                try:
                    sh.worksheet("SalesLog").append_row([str(doc_date), grand_total])
                except: pass
                
                # 2. Update Running No
                try:
                    prefix = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if prefix:
                        nxt = f"{prefix.group(1)}{str(int(prefix.group(2))+1).zfill(len(prefix.group(2)))}"
                        cell = ws_conf.find(run_key)
                        ws_conf.update_cell(cell.row, 2, nxt)
                except: pass
                
                # 3. Gen PDF
                d_data = {
                    "shop_name": st.session_state.s_n, "shop_tax": st.session_state.s_t, "shop_addr": st.session_state.s_a,
                    "cust_name": st.session_state.f_n, "cust_tax": st.session_state.f_t, "cust_addr": st.session_state.f_a, "cust_tel": st.session_state.f_tel
                }
                pdf = generate_pdf_v107(d_data, st.session_state.cart, doc_type, run_no, str(doc_date), vat_inc, logo_up)
                
                # 4. Backup
                fname = f"INV_{run_no}.pdf"
                bk_msg = ""
                if use_backup:
                    if upload_via_webhook(pdf, fname): bk_msg = "✅ Backup OK"
                    else: bk_msg = "⚠️ Backup Failed"
                
                st.success(f"เรียบร้อย! {bk_msg}")
                st.download_button("⬇️ Download PDF", pdf, fname, "application/pdf")
                st.session_state.cart = [] # Clear
