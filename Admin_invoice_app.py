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

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook เดิม
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# Load Font
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except:
    FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. Smart Connection (Auto-Retry System)
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
    """ฟังก์ชันอัจฉริยะ: ถ้า Quota เต็ม จะรอแล้วลองใหม่ให้เอง"""
    retries = 3
    for i in range(retries):
        try:
            return func(*args)
        except Exception as e:
            if "429" in str(e) or "Quota exceeded" in str(e):
                time.sleep(2 * (i + 1)) # รอ 2, 4, 6 วินาที
                continue
            else:
                raise e
    return func(*args) # ลองครั้งสุดท้าย

# Cache ข้อมูลนิ่งๆ ไว้นานๆ (1 ชม.) เพื่อไม่กิน Quota
@st.cache_data(ttl=3600)
def load_static_data():
    try:
        client = get_client()
        sh = client.open(SHEET_NAME)
        # ใช้ smart_request ห่อหุ้มการอ่าน
        items = smart_request(lambda: pd.DataFrame(sh.worksheet("Items").get_all_records()))
        custs = smart_request(lambda: pd.DataFrame(sh.worksheet("Customers").get_all_records()))
        return items, custs
    except:
        return pd.DataFrame(), pd.DataFrame()

# ข้อมูลที่ต้องสดใหม่เสมอ (Config / Queue)
def load_live_data():
    client = get_client()
    sh = client.open(SHEET_NAME)
    ws_conf = sh.worksheet("Config")
    # อ่าน Config แบบดิบๆ แล้วแปลงเอง (ประหยัดกว่า .acell หลายครั้ง)
    data = smart_request(ws_conf.get_all_values)
    conf = {str(r[0]): str(r[1]) for r in data if len(r) >= 2}
    
    try: ws_q = sh.worksheet("Queue")
    except: ws_q = None
    
    return sh, ws_conf, conf, ws_q

def upload_via_webhook(pdf_bytes, filename):
    try:
        payload = {
            "filename": filename, "mimeType": "application/pdf",
            "file": base64.b64encode(pdf_bytes).decode('utf-8'), "folderId": DRIVE_FOLDER_ID
        }
        requests.post(APPS_SCRIPT_URL, json=payload)
        return True
    except: return False

# ==========================================
# 🖨️ 3. PDF Generator (Fixed Coordinates)
# ==========================================
def generate_pdf_v110(doc_data, items, doc_type, run_no, date_str, vat_inc, logo_upload):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 # 210 x 297 mm
    
    def draw_form(base_y, is_copy):
        """
        base_y = จุดล่างสุดของฟอร์ม (0 สำหรับล่าง, 148.5mm สำหรับบน)
        เราจะวาดโดยอิงจาก base_y ขึ้นไปหา top
        """
        # กรอบพื้นที่ทำงาน (สูง 140mm)
        area_h = 140*mm
        margin = 15*mm
        top_y = base_y + area_h
        
        # 1. Logo
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                c.drawImage(img, margin, top_y - 15*mm, width=25*mm, height=12*mm, mask='auto', preserveAspectRatio=True)
            except: pass

        # 2. Shop Box (Right)
        box_w = 80*mm; box_h = 22*mm
        box_x = width - margin - box_w
        box_y = top_y - 20*mm
        
        c.setLineWidth(0.5)
        c.roundRect(box_x, box_y, box_w, box_h, 4, stroke=1, fill=0)
        
        c.setFont(FONT_NAME, 11) # Shop Name
        c.drawString(box_x + 2*mm, box_y + box_h - 5*mm, doc_data['s_n'])
        
        c.setFont(FONT_NAME, 9) # Address
        addr_lines = [doc_data['s_a'][i:i+55] for i in range(0, len(doc_data['s_a']), 55)]
        ay = box_y + box_h - 9*mm
        for l in addr_lines[:3]:
            c.drawString(box_x + 2*mm, ay, l)
            ay -= 3.5*mm

        # 3. Header Title
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        prefix = "สำเนา " if is_copy else "ต้นฉบับ "
        c.setFont(FONT_NAME, 14)
        c.drawCentredString(width/2, top_y - 28*mm, prefix + title)

        # 4. Info Line
        info_y = top_y - 35*mm
        c.setFont(FONT_NAME, 10)
        c.drawString(margin, info_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['s_t']}")
        c.drawRightString(width - margin, info_y, f"เลขที่ : {run_no}")

        # 5. Customer & Doc Box
        rect_y = info_y - 2*mm
        rect_h = 25*mm
        rect_btm = rect_y - rect_h
        
        c.rect(margin, rect_btm, width - 2*margin, rect_h)
        split_x = width - margin - 60*mm
        c.line(split_x, rect_y, split_x, rect_btm)
        
        # Left (Cust)
        cx = margin + 2*mm; cy = rect_y - 4*mm
        c.drawString(cx, cy, f"ชื่อลูกค้า : {doc_data['c_n']}")
        c.drawString(cx, cy - 5*mm, f"Tax ID : {doc_data['c_t']}")
        c.drawString(cx, cy - 10*mm, f"ที่อยู่ : {doc_data['c_a'][:60]}")
        c.drawString(cx, cy - 14*mm, f"       {doc_data['c_a'][60:110]}")
        c.drawString(cx, cy - 19*mm, f"โทร : {doc_data['c_tel']}")
        
        # Right (Doc)
        dx = split_x + 2*mm; dy = rect_y - 4*mm
        c.drawString(dx, dy, f"วันที่ : {date_str}")
        c.drawString(dx, dy - 5*mm, "ผู้ขาย : -")
        c.drawString(dx, dy - 10*mm, "เครดิต : สด")

        # 6. Items Table
        tbl_top = rect_btm - 2*mm
        tbl_h = 60*mm # Fixed height table
        tbl_btm = tbl_top - tbl_h
        
        # Draw Box & Header
        c.rect(margin, tbl_btm, width - 2*margin, tbl_h)
        c.line(margin, tbl_top - 6*mm, width - margin, tbl_top - 6*mm) # Header Line
        
        cols = [10*mm, 85*mm, 15*mm, 25*mm] # Cols widths (No, Item, Qty, Price) -> Total is remainder
        x_pos = [margin + sum(cols[:i]) for i in range(len(cols)+1)]
        x_total = width - margin
        
        # Vertical Lines
        c.line(x_pos[1], tbl_top, x_pos[1], tbl_btm) # After No
        c.line(x_pos[2], tbl_top, x_pos[2], tbl_btm) # After Item
        c.line(x_pos[3], tbl_top, x_pos[3], tbl_btm) # After Qty
        c.line(x_pos[4], tbl_top, x_pos[4], tbl_btm) # After Price
        
        # Header Text
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "หน่วยละ", "จำนวนเงิน"]
        c.setFont(FONT_NAME, 10)
        c.drawCentredString((margin+x_pos[1])/2, tbl_top - 4*mm, headers[0])
        c.drawCentredString((x_pos[1]+x_pos[2])/2, tbl_top - 4*mm, headers[1])
        c.drawCentredString((x_pos[2]+x_pos[3])/2, tbl_top - 4*mm, headers[2])
        c.drawCentredString((x_pos[3]+x_pos[4])/2, tbl_top - 4*mm, headers[3])
        c.drawCentredString((x_pos[4]+x_total)/2, tbl_top - 4*mm, headers[4])
        
        # Items Data
        curr_y = tbl_top - 10*mm
        total = 0
        for i, item in enumerate(items, 1):
            if i > 10: break
            name = item['name']; qty = item['qty']; price = item['price']
            amt = qty * price; total += amt
            
            c.drawCentredString((margin+x_pos[1])/2, curr_y, str(i))
            c.drawString(x_pos[1]+1*mm, curr_y, name[:45])
            c.drawRightString(x_pos[3]-1*mm, curr_y, f"{qty:,.0f}")
            c.drawRightString(x_pos[4]-1*mm, curr_y, f"{price:,.2f}")
            c.drawRightString(x_total-1*mm, curr_y, f"{amt:,.2f}")
            curr_y -= 5*mm

        # 7. Footer
        ft_y = tbl_btm
        if vat_inc:
            grand = total; pre = total * 100/107; vat = total - pre
        else:
            pre = total; vat = total * 0.07; grand = total + vat
            
        c.rect(x_pos[4], ft_y - 25*mm, x_total - x_pos[4], 25*mm) # Right Box
        c.rect(margin, ft_y - 25*mm, x_pos[4] - margin, 25*mm) # Left Box (Signature)
        
        # Values
        lbls = ["รวมเงิน", "ส่วนลด", "มูลค่า", "VAT 7%", "สุทธิ"]
        vals = [total, 0, pre, vat, grand]
        fy = ft_y - 4*mm
        for l, v in zip(lbls, vals):
            c.drawRightString(x_pos[4]+23*mm, fy, l)
            c.drawRightString(x_total-1*mm, fy, f"{v:,.2f}")
            fy -= 4.5*mm
            
        # Signature
        c.drawString(margin+5*mm, ft_y - 15*mm, "ลงชื่อผู้รับ ........................................")
        c.drawString(margin+5*mm, ft_y - 22*mm, "วันที่ ........................................")

    # Draw Top (Original)
    draw_form(height/2 + 5*mm, False)
    
    # Draw Dotted Line
    c.setDash(3, 3)
    c.line(5*mm, height/2, width-5*mm, height/2)
    c.setDash(1, 0)
    
    # Draw Bottom (Copy)
    draw_form(0, True)
    
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 4. State & Init
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['f_n','f_t','f_a','f_tel','s_n','s_t','s_a']:
    if k not in st.session_state: st.session_state[k] = ""

# Sidebar
with st.sidebar:
    st.title("Admin V110")
    if not st.session_state.logged_in:
        pwd = st.text_input("รหัสผ่าน", type="password")
        if st.button("เข้าสู่ระบบ"):
            if pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
            else: st.error("ผิด")
        st.stop()
    else:
        if st.button("🚪 ออกจากระบบ"): st.session_state.logged_in = False; st.rerun()
        if st.button("🔄 รีโหลดข้อมูล (แก้ Quota)"): st.cache_data.clear(); st.rerun()

# Load Data
try:
    # 1. Config (Live)
    sh, ws_conf, conf, ws_q = load_live_data()
    # 2. Static (Cached)
    item_df, cust_df = load_static_data()
    
    # Init Shop State
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName", "")
        st.session_state.s_t = conf.get("TaxID", "")
        st.session_state.s_a = conf.get("Address", "")
except Exception as e:
    st.error(f"เชื่อมต่อฐานข้อมูลไม่ได้ (Quota เต็ม): {e}")
    st.stop()

# ==========================================
# 🖥️ 5. UI Layout
# ==========================================
st.title("🧾 Nami Invoice (V110 Stable)")

col_L, col_R = st.columns([1.2, 1])

with col_L:
    with st.expander("🏠 ข้อมูลร้าน & โลโก้", expanded=True):
        c1, c2 = st.columns(2)
        st.session_state.s_n = c1.text_input("ชื่อร้าน", st.session_state.s_n)
        st.session_state.s_t = c2.text_input("Tax ID", st.session_state.s_t)
        st.session_state.s_a = st.text_area("ที่อยู่", st.session_state.s_a, height=80)
        logo_up = st.file_uploader("โลโก้ (PNG/JPG)", type=['png','jpg','jpeg'])
        
        if st.button("💾 บันทึกข้อมูลร้าน"):
            try:
                # บันทึกแบบระบุเซลล์ตรงๆ (ชัวร์สุด)
                smart_request(ws_conf.update_acell, 'B2', st.session_state.s_n)
                smart_request(ws_conf.update_acell, 'B3', st.session_state.s_t)
                smart_request(ws_conf.update_acell, 'B4', st.session_state.s_a)
                st.success("บันทึกสำเร็จ!")
            except: st.error("บันทึกไม่ได้ (ลองกดรีโหลด)")

    st.subheader("👤 ข้อมูลลูกค้า")
    cust_opts = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else [""]
    sel_cust = st.selectbox("🔍 ค้นหาลูกค้า", cust_opts)
    
    if sel_cust and sel_cust != st.session_state.get('last_c'):
        r = cust_df[cust_df['Name'] == sel_cust].iloc[0]
        st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
        st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
        st.session_state.last_c = sel_cust; st.rerun()

    c1, c2 = st.columns(2)
    st.session_state.f_n = c1.text_input("ชื่อลูกค้า", st.session_state.f_n)
    st.session_state.f_t = c2.text_input("Tax ID (ลูกค้า)", st.session_state.f_t)
    st.session_state.f_a = st.text_area("ที่อยู่ลูกค้า", st.session_state.f_a)
    st.session_state.f_tel = st.text_input("เบอร์โทร", st.session_state.f_tel)
    
    if st.button("🧹 ล้างค่าลูกค้า"):
        for k in ['f_n','f_t','f_a','f_tel']: st.session_state[k] = ""
        st.rerun()

    st.divider()
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    run_no = st.text_input("เลขที่เอกสาร", value=conf.get(run_key, "INV-000"))
    vat_inc = st.checkbox("รวม VAT แล้ว", value=True)

with col_R:
    st.subheader("🛒 รายการสินค้า")
    item_opts = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else [""]
    sel_item = st.selectbox("สินค้า", item_opts)
    c1, c2, c3 = st.columns([1,1,1])
    qty = c1.number_input("จำนวน", 1, value=1)
    price = c2.number_input("ราคา", 0.0)
    if c3.button("➕ เพิ่ม") and sel_item:
        st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        df_cart = pd.DataFrame(st.session_state.cart)
        df_cart['Total'] = df_cart['qty'] * df_cart['price']
        st.dataframe(df_cart, use_container_width=True, hide_index=True)
        grand = df_cart['Total'].sum()
        st.info(f"💰 รวม: {grand:,.2f}")
        
        if st.button("❌ ลบรายการล่าสุด"): st.session_state.cart.pop(); st.rerun()
        
        st.divider()
        use_bk = st.checkbox("Backup ลง Drive", value=True)
        
        if st.button("🖨️ ออกใบกำกับภาษี", type="primary", use_container_width=True):
            if not st.session_state.f_n: st.error("ระบุชื่อลูกค้า"); st.stop()
            
            with st.spinner("Processing..."):
                # 1. Update Sheets (SalesLog & Config)
                try:
                    # Update Config
                    p = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if p:
                        nxt = f"{p.group(1)}{str(int(p.group(2))+1).zfill(len(p.group(2)))}"
                        t_cell = 'B5' if doc_type == "Full" else 'B6'
                        smart_request(ws_conf.update_acell, t_cell, nxt)
                    
                    # SalesLog
                    smart_request(sh.worksheet("SalesLog").append_row, [datetime.now().strftime("%Y-%m-%d"), grand])
                    
                    # Clear Queue
                    if st.session_state.get('q_idx'):
                        smart_request(ws_q.update_cell, st.session_state.q_idx, 10, "Done")
                        st.session_state.q_idx = None
                except Exception as e: st.warning(f"บันทึกชีตไม่ได้ (แต่ไฟล์จะได้): {e}")
                
                # 2. PDF
                d_data = {
                    "s_n": st.session_state.s_n, "s_t": st.session_state.s_t, "s_a": st.session_state.s_a,
                    "c_n": st.session_state.f_n, "c_t": st.session_state.f_t, "c_a": st.session_state.f_a, "c_tel": st.session_state.f_tel
                }
                pdf = generate_pdf_v110(d_data, st.session_state.cart, doc_type, run_no, datetime.now().strftime("%d/%m/%Y"), vat_inc, logo_up)
                fname = f"INV_{run_no}.pdf"
                
                # 3. Backup
                bk_msg = ""
                if use_bk:
                    if upload_via_webhook(pdf.getvalue(), fname): bk_msg = "✅ Backup OK"
                    else: bk_msg = "⚠️ Backup Failed"
                
                st.success(f"เสร็จสิ้น! {bk_msg}")
                st.download_button("⬇️ Download PDF", pdf, fname, "application/pdf")
                st.session_state.cart = [] # Clear

# Sidebar Queue
with st.sidebar:
    st.divider()
    if ws_q:
        try:
            q_recs = smart_request(ws_q.get_all_records)
            q_df = pd.DataFrame(q_recs)
            pending = q_df[q_df['Status'] != 'Done']
            for i, r in pending.iterrows():
                st.info(f"{r['Name']} ({r['Price']})")
                if st.button("ดึง", key=f"q_{i}"):
                    st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
                    st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
                    st.session_state.q_idx = i + 2
                    if r['Item']:
                        try: p = float(str(r['Price']).replace(',',''))
                        except: p = 0.0
                        st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": p}]
                    st.rerun()
        except: st.caption("No Queue")
