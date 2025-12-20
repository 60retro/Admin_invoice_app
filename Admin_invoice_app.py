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
# ⚙️ 1. Config
# ==========================================
st.set_page_config(page_title="Nami Admin V110", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "1234"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook ตรงนี้
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur" # ใส่ ID โฟลเดอร์

try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
    FONT_SIZE = 12
except:
    FONT_NAME = 'Helvetica'
    FONT_SIZE = 10

# ==========================================
# 🔌 2. Database & Logic (FIXED)
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. สร้าง Credentials (กุญแจ)
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    
    # 2. 🟢 FIX: Authorize (ไขประตู) ก่อนส่งคืน
    return gspread.authorize(creds)

def load_data():
    try:
        client = get_client()
        sh = client.open(SHEET_NAME)
        
        # 1. Config (อ่านแบบระบุเซลล์ B2, B3...)
        ws_c = sh.worksheet("Config")
        s_name = ws_c.acell('B2').value
        s_tax = ws_c.acell('B3').value
        s_addr = ws_c.acell('B4').value
        full_run = ws_c.acell('B5').value
        abb_run = ws_c.acell('B6').value
        
        # 2. Customers & Items
        try: custs = pd.DataFrame(sh.worksheet("Customers").get_all_records())
        except: custs = pd.DataFrame(columns=["Name"])
        try: items = pd.DataFrame(sh.worksheet("Items").get_all_records())
        except: items = pd.DataFrame(columns=["ItemName"])
        
        # 3. Queue
        try: ws_q = sh.worksheet("Queue")
        except: ws_q = None
        
        return sh, ws_c, s_name, s_tax, s_addr, full_run, abb_run, custs, items, ws_q
    except Exception as e:
        st.error(f"โหลดข้อมูลไม่ได้: {e}")
        return None, None, "", "", "", "", "", pd.DataFrame(), pd.DataFrame(), None

def save_shop_config(sh, name, tax, addr):
    try:
        ws = sh.worksheet("Config")
        ws.update_acell('B2', name)
        ws.update_acell('B3', tax)
        ws.update_acell('B4', addr)
        return True
    except: return False

def upload_to_drive(pdf_bytes, filename):
    try:
        payload = {
            "filename": filename, "mimeType": "application/pdf",
            "file": base64.b64encode(pdf_bytes).decode('utf-8'), "folderId": DRIVE_FOLDER_ID
        }
        requests.post(APPS_SCRIPT_URL, json=payload)
        return True
    except: return False

# ==========================================
# 🖨️ 3. PDF Engine (Precision Layout)
# ==========================================
def generate_pdf_precise(data, items, doc_type, run_no, date_str, is_vat, logo_data):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 # 210mm x 297mm
    
    def draw_section(y_start, is_copy):
        base_y = y_start - 148.5*mm if y_start == 297*mm else 0
        
        # 1. Logo
        if logo_data:
            try:
                logo_data.seek(0)
                img = ImageReader(logo_data)
                c.drawImage(img, 15*mm, y_start - 25*mm, width=30*mm, height=15*mm, mask='auto', preserveAspectRatio=True)
            except: pass

        # 2. Shop Box
        box_w = 90*mm; box_h = 25*mm
        box_x = width - 15*mm - box_w
        box_y = y_start - 30*mm
        
        c.setLineWidth(0.5)
        c.roundRect(box_x, box_y, box_w, box_h, 5, stroke=1, fill=0)
        
        c.setFont(FONT_NAME, 12)
        c.drawString(box_x + 3*mm, box_y + box_h - 6*mm, str(data['s_n']))
        
        c.setFont(FONT_NAME, 10)
        addr = str(data['s_a'])
        # Simple wrap logic for address
        lines = []
        while len(addr) > 55:
            split = addr[:55].rfind(' ')
            if split == -1: split = 55
            lines.append(addr[:split])
            addr = addr[split:].strip()
        lines.append(addr)
        
        ay = box_y + box_h - 11*mm
        for l in lines[:3]:
            c.drawString(box_x + 3*mm, ay, l)
            ay -= 4*mm
        
        # 3. Header Title
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        prefix = "สำเนา " if is_copy else "ต้นฉบับ "
        c.setFont(FONT_NAME, 16)
        c.drawCentredString(width/2, y_start - 40*mm, prefix + title)
        
        # 4. Info Bar
        bar_y = y_start - 50*mm
        c.setFont(FONT_NAME, 11)
        c.drawString(15*mm, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {data['s_t']}")
        c.drawRightString(width - 15*mm, bar_y, f"เลขที่ : {run_no}")
        
        # 5. Customer & Doc Info (Big Box)
        rect_top = bar_y - 2*mm
        rect_h = 28*mm
        rect_btm = rect_top - rect_h
        
        c.rect(15*mm, rect_btm, width - 30*mm, rect_h)
        c.line(width/2 + 20*mm, rect_top, width/2 + 20*mm, rect_btm)
        
        # Left Info
        lx = 18*mm; ly = rect_top - 5*mm
        c.drawString(lx, ly, f"ชื่อลูกค้า : {data['c_n']}")
        c.drawString(lx, ly - 6*mm, f"ที่อยู่ : {str(data['c_a'])[:50]}")
        c.drawString(lx, ly - 10*mm, f"       {str(data['c_a'])[50:100]}")
        c.drawString(lx, ly - 16*mm, f"Tax ID : {data['c_t']}")
        c.drawString(lx, ly - 22*mm, f"โทร : {data['c_tel']}")
        
        # Right Info
        rx = width/2 + 23*mm; ry = rect_top - 5*mm
        c.drawString(rx, ry, f"วันที่ : {date_str}")
        c.drawString(rx, ry - 6*mm, "พนักงานขาย : -")
        c.drawString(rx, ry - 12*mm, "เงื่อนไข : สด")
        
        # 6. Items Table
        tbl_header_y = rect_btm - 2*mm
        c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(15*mm, tbl_header_y - 7*mm, width - 30*mm, 7*mm, fill=1, stroke=1)
        c.setFillColorRGB(0,0,0)
        
        xs = [15*mm, 25*mm, 120*mm, 140*mm, 170*mm, width-15*mm]
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "หน่วยละ", "จำนวนเงิน"]
        c.setFont(FONT_NAME, 11)
        
        c.drawCentredString((xs[0]+xs[1])/2, tbl_header_y - 5*mm, headers[0])
        c.drawString(xs[1]+2*mm, tbl_header_y - 5*mm, headers[1])
        c.drawCentredString((xs[2]+xs[3])/2, tbl_header_y - 5*mm, headers[2])
        c.drawCentredString((xs[3]+xs[4])/2, tbl_header_y - 5*mm, headers[3])
        c.drawCentredString((xs[4]+xs[5])/2, tbl_header_y - 5*mm, headers[4])
        
        y_item = tbl_header_y - 7*mm
        total_val = 0
        for i, item in enumerate(items, 1):
            if i > 10: break
            name = str(item['name']); qty = item['qty']; price = item['price']
            amt = qty * price; total_val += amt
            
            y_item -= 7*mm
            c.drawCentredString((xs[0]+xs[1])/2, y_item+2*mm, str(i))
            c.drawString(xs[1]+2*mm, y_item+2*mm, name[:50])
            c.drawRightString(xs[3]-2*mm, y_item+2*mm, f"{qty:,.0f}")
            c.drawRightString(xs[4]-2*mm, y_item+2*mm, f"{price:,.2f}")
            c.drawRightString(xs[5]-2*mm, y_item+2*mm, f"{amt:,.2f}")
            
        table_btm = rect_btm - 90*mm
        c.rect(15*mm, table_btm, width-30*mm, 90*mm)
        for x in xs[1:-1]:
            c.line(x, tbl_header_y, x, table_btm)
            
        # 7. Summary
        if is_vat:
            grand = total_val; pre = total_val*100/107; vat = total_val - pre
        else:
            pre = total_val; vat = total_val*0.07; grand = total_val + vat
            
        sum_y = table_btm
        c.line(xs[4], sum_y, xs[4], sum_y - 35*mm)
        c.line(xs[5], sum_y, xs[5], sum_y - 35*mm)
        c.rect(xs[4], sum_y - 35*mm, xs[5]-xs[4], 35*mm)
        c.rect(15*mm, sum_y - 35*mm, width-30*mm, 35*mm)
        
        lbls = ["รวมเงิน", "ส่วนลด", "มูลค่าสินค้า", "VAT 7%", "ยอดสุทธิ"]
        vals = [total_val, 0, pre, vat, grand]
        
        curr_sy = sum_y - 6*mm
        for l, v in zip(lbls, vals):
            c.drawRightString(xs[4]-2*mm, curr_sy, l)
            c.drawRightString(xs[5]-2*mm, curr_sy, f"{v:,.2f}")
            c.line(xs[4], curr_sy-1*mm, xs[5], curr_sy-1*mm)
            curr_sy -= 7*mm
            
        sig_y = curr_sy - 10*mm
        c.drawString(15*mm + 10*mm, sig_y, "ผู้รับสินค้า ............................................")
        c.drawString(width - 15*mm - 60*mm, sig_y, "ผู้รับเงิน ............................................")

    draw_section(height, False)
    c.setDash(2, 2)
    c.line(5*mm, height/2, width-5*mm, height/2)
    c.setDash(1, 0)
    draw_section(height/2, True)
    
    c.save()
    buffer.seek(0)
    return buffer

# ==========================================
# 🖥️ 4. UI Logic
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['f_n','f_t','f_a','f_tel']: 
    if k not in st.session_state: st.session_state[k] = ""

# Sidebar
with st.sidebar:
    st.title("Admin Menu")
    
    if st.session_state.logged_in:
        if st.button("🔄 Sync DB"): st.rerun()
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False; st.rerun()
    else:
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
            else: st.error("ผิด")
        st.stop()

# Load Data
sh, ws_c, s_n, s_t, s_a, f_run, a_run, cust_df, item_df, ws_q = load_data()

# Main UI
st.title("🧾 Nami Invoice (V110 Final)")

if not sh: # ถ้าโหลดไม่ได้
    st.error("เชื่อมต่อ Database ไม่ได้ กรุณาเช็ค Internet หรือ Quota")
    st.stop()

tab1, tab2 = st.tabs(["📝 ออกบิล", "☁️ คิว"])

with tab1:
    with st.expander("🏠 ข้อมูลร้าน & โลโก้"):
        c1, c2 = st.columns(2)
        new_sn = c1.text_input("ชื่อร้าน", value=s_n)
        new_st = c2.text_input("Tax ID", value=s_t)
        new_sa = st.text_area("ที่อยู่", value=s_a, height=80)
        uploaded_logo = st.file_uploader("โลโก้ (PNG/JPG)", type=['png','jpg'])
        if st.button("บันทึกข้อมูลร้าน"):
            if save_shop_config(sh, new_sn, new_st, new_sa): st.success("บันทึกแล้ว!")
            else: st.error("บันทึกไม่สำเร็จ")

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("ลูกค้า")
        c_list = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else []
        sel_c = st.selectbox("ค้นหาลูกค้าเก่า", c_list)
        if sel_c and sel_c != st.session_state.get('lc'):
            r = cust_df[cust_df['Name']==sel_c].iloc[0]
            st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
            st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
            st.session_state.lc = sel_c; st.rerun()
            
        st.session_state.f_n = st.text_input("ชื่อลูกค้า", st.session_state.f_n)
        st.session_state.f_t = st.text_input("เลขผู้เสียภาษี", st.session_state.f_t)
        st.session_state.f_a = st.text_area("ที่อยู่ลูกค้า", st.session_state.f_a)
        st.session_state.f_tel = st.text_input("เบอร์โทร", st.session_state.f_tel)
        
        if st.button("ล้างค่าลูกค้า"):
            st.session_state.f_n = ""; st.session_state.f_t = ""; st.session_state.f_a = ""; st.session_state.f_tel = ""
            st.rerun()

    with col_d:
        st.subheader("เอกสาร")
        d_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
        curr_run = f_run if d_type == "Full" else a_run
        run_no = st.text_input("เลขที่เอกสาร", value=curr_run)
        d_date = st.date_input("วันที่", datetime.now())
        vat_inc = st.checkbox("รวม VAT แล้ว", value=True)
        
        st.markdown("### สินค้า")
        i_list = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else []
        s_item = st.selectbox("เลือกสินค้า", i_list)
        q = st.number_input("จำนวน", 1, 100, 1)
        p = st.number_input("ราคา", 0.0)
        if st.button("เพิ่มสินค้า"):
            if s_item: st.session_state.cart.append({"name": s_item, "qty": q, "price": p})

    st.divider()
    if st.session_state.cart:
        cdf = pd.DataFrame(st.session_state.cart)
        cdf['Total'] = cdf['qty'] * cdf['price']
        st.dataframe(cdf, use_container_width=True)
        st.metric("ยอดรวมสุทธิ", f"{cdf['Total'].sum():,.2f}")
        
        if st.button("ลบรายการล่าสุด"): st.session_state.cart.pop(); st.rerun()
        
        st.markdown("---")
        use_bk = st.checkbox("Backup ลง Drive", value=True)
        
        if st.button("🖨️ ยืนยันการออกบิล", type="primary", use_container_width=True):
            if not st.session_state.f_n: st.error("ระบุชื่อลูกค้า"); st.stop()
            
            with st.spinner("Processing..."):
                d_data = {
                    "s_n": new_sn, "s_t": new_st, "s_a": new_sa,
                    "c_n": st.session_state.f_n, "c_t": st.session_state.f_t,
                    "c_a": st.session_state.f_a, "c_tel": st.session_state.f_tel
                }
                
                # 1. Update Sheet
                try:
                    prefix = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if prefix:
                        nxt = f"{prefix.group(1)}{str(int(prefix.group(2))+1).zfill(len(prefix.group(2)))}"
                        t_cell = 'B5' if d_type == "Full" else 'B6'
                        ws_c.update_acell(t_cell, nxt)
                    sh.worksheet("SalesLog").append_row([str(d_date), cdf['Total'].sum()])
                    if st.session_state.get('q_idx'):
                        ws_q.update_cell(st.session_state.q_idx, 10, "Done")
                        st.session_state.q_idx = None
                except: st.warning("Sheet Update Error")
                
                # 2. Gen PDF
                pdf = generate_pdf_precise(d_data, st.session_state.cart, d_type, run_no, str(d_date), vat_inc, uploaded_logo)
                fname = f"INV_{run_no}.pdf"
                
                # 3. Backup
                msg = ""
                if use_bk:
                    if upload_to_drive(pdf.getvalue(), fname): msg = "✅ Backup OK"
                    else: msg = "⚠️ Backup Failed"
                
                st.success(f"เสร็จสิ้น! {msg}")
                st.download_button("ดาวน์โหลด PDF", pdf, fname, "application/pdf")
                st.session_state.cart = []

with tab2:
    if st.button("Refresh Queue"): st.rerun()
    if ws_q:
        try:
            q_recs = ws_q.get_all_records()
            for i, r in enumerate(q_recs):
                if r['Status'] != 'Done':
                    with st.container(border=True):
                        c1, c2 = st.columns([3, 1])
                        c1.write(f"**{r['Name']}** ({r['Price']})")
                        if c2.button("ดึง", key=f"q_{i}"):
                            st.session_state.f_n = r['Name']
                            st.session_state.f_t = str(r['TaxID'])
                            st.session_state.f_a = f"{r['Address1']} {r['Address2']}"
                            st.session_state.f_tel = str(r['Phone'])
                            st.session_state.q_idx = i + 2
                            if r['Item']:
                                try: pr = float(str(r['Price']).replace(',',''))
                                except: pr = 0.0
                                st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": pr}]
                            st.rerun()
        except: st.info("No Queue")
