import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
from io import BytesIO
import requests
import base64
import time
import math
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
st.set_page_config(page_title="Nami Admin V112 (Direct Port)", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook เดิม
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# Load Font (ใช้ชื่อเดียวกับ Desktop App เพื่อความเป๊ะ)
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME_STD = 'CustomFont'
    FONT_NAME_BOLD = 'CustomFont' 
except:
    FONT_NAME_STD = 'Helvetica'
    FONT_NAME_BOLD = 'Helvetica-Bold'

# ==========================================
# 🔌 2. Smart Connection (Anti-Quota)
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
    """ระบบรออัตโนมัติเมื่อ Google บอกว่า Quota เต็ม"""
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
# 🖨️ 3. PDF Generator (PORTED DIRECTLY FROM V87)
# ==========================================
def generate_pdf_v87_port(doc_data, items, doc_type, run_no, date_str, vat_inc, logo_upload):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    half_height = height / 2

    # 🟢 1. คำนวณยอดเงินก่อน (Fix NameError)
    total = sum([x['qty'] * x['price'] for x in items])
    if vat_inc:
        g = total
        s = total / 1.07
        v = g - s
    else:
        s = total
        v = total * 0.07
        g = s + v
        g = math.floor(g) # Logic จาก Desktop Code

    # --- Helper from Desktop Code ---
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
        # 🟢 ตัวแปร Layout จาก Desktop Code V87
        margin = 15 * mm
        base_y = y_offset
        top_y = base_y + half_height - margin
        page_w = width - (2 * margin)
        font_std = 11
        font_bold = 12
        line_h = 12
        
        # --- Logo ---
        logo_w = 110; logo_h = 55
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                # ปรับตำแหน่ง Logo ตาม Desktop Code (top_y - logo_h + 5)
                c.drawImage(img, margin, top_y - logo_h + 5, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
            except: pass

        # --- Shop Box ---
        box_w = 260; box_h = 80
        box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        
        c.setFont(FONT_NAME_BOLD, font_bold)
        c.drawString(box_x + 10, box_y + box_h - 15, doc_data['s_n'])
        
        c.setFont(FONT_NAME_STD, font_std)
        raw_addr = doc_data['s_a'].split('\n')
        cur_sy = box_y + box_h - 30
        for line in raw_addr:
            wrapped = wrap_text_lines(line, box_w - 20, FONT_NAME_STD, font_std)
            for w in wrapped:
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w); cur_sy -= line_h

        # --- Title ---
        t_str = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        full_title = f"ต้นฉบับ {t_str}" if y_offset > 0 else f"สำเนา {t_str}"
        if doc_type == "ABB": full_title = t_str # ABB ไม่ต้องมีต้นฉบับ/สำเนา

        title_y = box_y - 20
        c.setFont(FONT_NAME_BOLD, font_bold + 2)
        # คำนวณ Center X ด้านซ้ายเหมือน Desktop
        center_x_left = margin + ((box_x - margin) / 2)
        c.drawCentredString(center_x_left, title_y, full_title)
        
        bar_y = title_y - 20
        c.setFont(FONT_NAME_STD, font_std)
        c.drawString(margin, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['s_t']}")
        c.drawRightString(width - margin, bar_y, f"เลขที่ : {run_no}")

        # --- Info Box ---
        info_box_y = bar_y - 5; info_box_h = 75; info_box_btm = info_box_y - info_box_h
        c.rect(margin, info_box_btm, page_w, info_box_h)
        div_x = width - margin - 200
        c.line(div_x, info_box_y, div_x, info_box_btm)
        
        cx = margin + 10; cy = info_box_y - 12; label_anchor = cx + 110
        c.setFont(FONT_NAME_BOLD, font_bold); c.drawRightString(label_anchor, cy, "เลขประจำตัวผู้เสียภาษีอากร :")
        c.setFont(FONT_NAME_STD, font_std); c.drawString(label_anchor + 5, cy, doc_data['c_t'])
        
        cy -= 12
        c.setFont(FONT_NAME_BOLD, font_bold); c.drawRightString(label_anchor, cy, "ชื่อลูกค้า :")
        c.setFont(FONT_NAME_STD, font_std)
        # คำนวณพื้นที่เหลือจริง
        avail_w = div_x - (label_anchor + 5) - 5
        for l in wrap_text_lines(doc_data['c_n'], avail_w, FONT_NAME_STD, font_std):
            c.drawString(label_anchor + 5, cy, l); cy -= 10
        cy -= 2
        
        c.setFont(FONT_NAME_BOLD, font_bold); c.drawRightString(label_anchor, cy, "ที่อยู่ :")
        c.setFont(FONT_NAME_STD, font_std)
        for l in wrap_text_lines(doc_data['c_a'], avail_w, FONT_NAME_STD, font_std):
            c.drawString(label_anchor + 5, cy, l); cy -= 10
            
        tel_y = info_box_btm + 5
        c.setFont(FONT_NAME_BOLD, font_bold); c.drawRightString(label_anchor, tel_y, "โทรศัพท์ :")
        c.setFont(FONT_NAME_STD, font_std); c.drawString(label_anchor + 5, tel_y, doc_data['c_tel'])

        dx = div_x + 10; dy = info_box_y - 12
        c.setFont(FONT_NAME_BOLD, font_bold)
        c.drawRightString(dx + 80, dy, "วันที่เอกสาร :"); c.drawRightString(dx + 80, dy - 12, "พนักงานขาย :"); c.drawRightString(dx + 80, dy - 24, "เงื่อนไขการชำระ :")
        c.setFont(FONT_NAME_STD, font_std)
        c.drawString(dx + 85, dy, date_str); c.drawString(dx + 85, dy - 24, "สด")

        # --- Table ---
        tbl_top = info_box_btm - 5
        c.setFillColorRGB(0.2, 0.2, 0.2); c.rect(margin, tbl_top - 14, page_w, 14, fill=1, stroke=1)
        c.setFillColorRGB(1, 1, 1)
        
        # 🔴 Col Widths from Desktop Code
        col_w = [25, page_w - 215, 45, 70, 75]
        col_x = [margin, margin+col_w[0], margin+col_w[0]+col_w[1], margin+col_w[0]+col_w[1]+col_w[2], margin+col_w[0]+col_w[1]+col_w[2]+col_w[3]]
        
        c.setFont(FONT_NAME_BOLD, font_bold)
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]
        for i, h in enumerate(headers): c.drawCentredString(col_x[i] + col_w[i]/2, tbl_top - 10, h)
        c.setFillColorRGB(0, 0, 0)
        
        curr_y = tbl_top - 14
        c.setFont(FONT_NAME_STD, font_std)
        
        for idx, item in enumerate(items, 1):
            if idx > 15: break
            nm = item['name']; qty = item['qty']; price = item['price']
            amt = qty * price
            
            nm_lines = wrap_text_lines(str(nm), col_w[1] - 10, FONT_NAME_STD, font_std)
            if len(nm_lines) > 3: nm_lines = nm_lines[:3]
            
            txt_y = curr_y - 12
            c.drawCentredString(col_x[0] + col_w[0]/2, txt_y, str(idx))
            for i, l in enumerate(nm_lines): c.drawString(col_x[1] + 5, txt_y - (i*12), l)
            c.drawRightString(col_x[2] + col_w[2] - 10, txt_y, f"{qty:,.0f}")
            c.drawRightString(col_x[3] + col_w[3] - 5, txt_y, f"{price:,.2f}")
            c.drawRightString(col_x[4] + col_w[4] - 5, txt_y, f"{amt:,.2f}")
            
            curr_y -= 45 # row height
            c.setLineWidth(0.5); c.line(margin, curr_y, width - margin, curr_y)
            
        btm = curr_y
        c.rect(margin, btm, page_w, (tbl_top - 14) - btm)
        for x in col_x[1:]: c.line(x, tbl_top - 14, x, btm)
        
        # --- Footer ---
        f_top = btm; row_h = 14
        lbls = ["จำนวนเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        vals = [f"{s+v:,.2f}", "-", f"{s:,.2f}", f"{v:,.2f}", f"{g:,.2f}"]
        
        c.line(col_x[4], f_top, col_x[4], f_top - (5 * row_h))
        c.line(width - margin, f_top, width - margin, f_top - (5 * row_h))
        
        for i in range(5):
            r_top = f_top - (i * row_h); r_btm = r_top - row_h; t_y = r_btm + 4
            c.line(col_x[4], r_btm, width - margin, r_btm)
            c.setFont(FONT_NAME_BOLD, font_std); c.drawRightString(col_x[4] - 15, t_y, lbls[i] + " :")
            if i == 4: c.setFont(FONT_NAME_BOLD, font_bold)
            else: c.setFont(FONT_NAME_STD, font_std)
            c.drawRightString(width - margin - 5, t_y, vals[i])
            
        sig_y = f_top - (5 * row_h) - 25
        c.setFont(FONT_NAME_STD, font_std)
        c.drawString(margin + 20, sig_y, "ผู้รับสินค้า ...........................................................")
        c.drawString(width - margin - 220, sig_y, "ผู้รับเงิน ...........................................................")

    # Draw Logic (Original & Copy)
    if doc_type == "ABB":
        draw_invoice(half_height)
    else:
        draw_invoice(half_height)
        c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0)
        draw_invoice(0)
    
    c.save(); buffer.seek(0)
    # 🟢 Return ไฟล์ และ ยอดเงิน (ที่คำนวณไว้ข้างบน)
    return buffer, g

# ==========================================
# 🖥️ 4. UI Implementation (State Management)
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['s_n', 's_t', 's_a', 'c_n', 'c_t', 'c_a1', 'c_a2', 'c_tel']:
    if k not in st.session_state: st.session_state[k] = ""

with st.sidebar:
    st.title("Menu")
    if not st.session_state.logged_in:
        if st.button("Login") and st.text_input("Pwd", type="password") == ADMIN_PASSWORD:
            st.session_state.logged_in = True; st.rerun()
        st.stop()
    else:
        if st.button("Logout"): st.session_state.logged_in = False; st.rerun()
        if st.button("🔄 Sync DB"): st.cache_data.clear(); st.rerun()

# Load Data
try:
    sh, ws_conf, conf, ws_q = load_live_data()
    item_df, cust_df = load_static_data()
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName","")
        st.session_state.s_t = conf.get("TaxID","")
        st.session_state.s_a = conf.get("Address","")
except: st.error("DB Error (Quota)"); st.stop()

st.title("🧾 Invoice (Port from V87)")
col1, col2 = st.columns([1.2, 1])

with col1:
    with st.expander("🏠 ข้อมูลร้าน (แก้ไขได้)", expanded=True):
        st.session_state.s_n = st.text_input("ร้าน", st.session_state.s_n)
        st.session_state.s_t = st.text_input("Tax", st.session_state.s_t)
        st.session_state.s_a = st.text_area("ที่อยู่", st.session_state.s_a)
        logo_up = st.file_uploader("Logo", type=['png','jpg'])
        if st.button("Save Shop"):
            smart_request(ws_conf.update_acell, 'B2', st.session_state.s_n)
            smart_request(ws_conf.update_acell, 'B3', st.session_state.s_t)
            smart_request(ws_conf.update_acell, 'B4', st.session_state.s_a)
            st.success("Saved!")

    st.subheader("ลูกค้า")
    sel_c = st.selectbox("ค้นหา", [""] + list(cust_df['Name'].unique()) if not cust_df.empty else [])
    if sel_c and sel_c != st.session_state.get('lc'):
        r = cust_df[cust_df['Name']==sel_c].iloc[0]
        st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
        st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
        st.session_state.lc = sel_c; st.rerun()

    c1, c2 = st.columns(2)
    st.session_state.c_n = c1.text_input("ชื่อลูกค้า", st.session_state.f_n)
    st.session_state.c_t = c2.text_input("Tax ID", st.session_state.f_t)
    st.session_state.c_a = st.text_area("ที่อยู่", st.session_state.f_a)
    st.session_state.c_tel = st.text_input("โทร", st.session_state.f_tel)
    if st.button("Clear"):
        for k in ['f_n','f_t','f_a','f_tel']: st.session_state[k] = ""
        st.rerun()

    st.divider()
    doc_type = st.radio("Type", ["Full", "ABB"], horizontal=True)
    run_no = st.text_input("Doc No", value=conf.get("Full_No" if doc_type=="Full" else "Abb_No", "INV-000"))
    vat_inc = st.checkbox("VAT Included", value=True)

with col2:
    st.subheader("สินค้า")
    sel_i = st.selectbox("เลือก", [""] + list(item_df['ItemName'].unique()) if not item_df.empty else [])
    c_q, c_p, c_b = st.columns([1,1,1])
    q = c_q.number_input("Qty", 1); p = c_p.number_input("Price", 0.0)
    if c_b.button("Add") and sel_i: st.session_state.cart.append({"name": sel_i, "qty": q, "price": p})

    if st.session_state.cart:
        df = pd.DataFrame(st.session_state.cart); df['Total'] = df['qty']*df['price']
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.info(f"Total: {df['Total'].sum():,.2f}")
        if st.button("Del Last"): st.session_state.cart.pop(); st.rerun()
        
        st.divider()
        use_bk = st.checkbox("Backup", value=True)
        if st.button("🖨️ Print & Save", type="primary"):
            if not st.session_state.c_n: st.error("No Name"); st.stop()
            with st.spinner("Generating..."):
                # Gen PDF
                d_data = {'s_n': st.session_state.s_n, 's_t': st.session_state.s_t, 's_a': st.session_state.s_a,
                          'c_n': st.session_state.c_n, 'c_t': st.session_state.c_t, 'c_a': st.session_state.c_a, 'c_tel': st.session_state.c_tel}
                # Call Ported Function
                pdf, grand = generate_pdf_v87_port(d_data, st.session_state.cart, doc_type, run_no, datetime.now().strftime("%d/%m/%Y"), vat_inc, logo_up)
                
                # Update Sheet
                try:
                    smart_request(sh.worksheet("SalesLog").append_row, [datetime.now().strftime("%Y-%m-%d"), grand])
                    p = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if p:
                        nxt = f"{p.group(1)}{str(int(p.group(2))+1).zfill(len(p.group(2)))}"
                        t_cell = 'B5' if doc_type == "Full" else 'B6'
                        smart_request(ws_conf.update_acell, t_cell, nxt)
                    if st.session_state.get('q_idx'):
                        smart_request(ws_q.update_cell, st.session_state.q_idx, 10, "Done")
                        st.session_state.q_idx = None
                except: pass
                
                fname = f"INV_{run_no}.pdf"
                if use_bk: upload_via_webhook(pdf.getvalue(), fname)
                
                st.success("Done!")
                st.download_button("Download", pdf, fname, "application/pdf")
                st.session_state.cart = []

with st.sidebar:
    st.divider()
    if ws_q:
        try:
            q = pd.DataFrame(smart_request(ws_q.get_all_records))
            for i, r in q[q['Status']!='Done'].iterrows():
                if st.button(f"{r['Name']}", key=f"q_{i}"):
                    st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
                    st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
                    st.session_state.q_idx = i + 2
                    if r['Item']:
                        try: p = float(str(r['Price']).replace(',',''))
                        except: p = 0.0
                        st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": p}]
                    st.rerun()
        except: pass
