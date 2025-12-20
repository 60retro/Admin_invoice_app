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
st.set_page_config(page_title="Nami Admin V111", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "1234"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook เดิม
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"

# Load Font
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
    FONT_SIZE = 12
except:
    FONT_NAME = 'Helvetica'
    FONT_SIZE = 10

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
    """ระบบป้องกัน Error 429 (Quota Exceeded)"""
    for i in range(3):
        try:
            return func(*args)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e):
                time.sleep(2)
                continue
            raise e
    return func(*args)

@st.cache_data(ttl=600)
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
# 🖨️ 3. PDF Generator (Fixed Return Logic)
# ==========================================
def generate_pdf_v111(doc_data, items, doc_type, run_no, date_str, vat_inc, logo_upload):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4 # 210x297mm
    
    # 🟢 คำนวณยอดเงินก่อนวาด (แก้ NameError)
    total_raw = sum([x['qty'] * x['price'] for x in items])
    if vat_inc:
        grand_total = total_raw
        pre_vat = total_raw * 100 / 107
        vat_amt = total_raw - pre_vat
    else:
        pre_vat = total_raw
        vat_amt = total_raw * 0.07
        grand_total = total_raw + vat_amt

    def draw_form(base_y, is_copy):
        margin = 10*mm; top_y = base_y + 140*mm
        
        # 1. Logo
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                c.drawImage(img, margin, top_y - 15*mm, width=25*mm, height=12*mm, mask='auto', preserveAspectRatio=True)
            except: pass

        # 2. Shop Box
        box_w = 85*mm; box_h = 22*mm; box_x = width - margin - box_w; box_y = top_y - 20*mm
        c.setLineWidth(0.5); c.roundRect(box_x, box_y, box_w, box_h, 4, stroke=1, fill=0)
        c.setFont(FONT_NAME, 11); c.drawString(box_x + 2*mm, box_y + box_h - 5*mm, doc_data['s_n'])
        c.setFont(FONT_NAME, 9)
        addr = doc_data['s_a']
        al = [addr[i:i+60] for i in range(0, len(addr), 60)]
        ay = box_y + box_h - 9*mm
        for l in al[:3]: c.drawString(box_x + 2*mm, ay, l); ay -= 3.5*mm

        # 3. Header
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        prefix = "สำเนา " if is_copy else "ต้นฉบับ "
        c.setFont(FONT_NAME, 14); c.drawCentredString(width/2, top_y - 28*mm, prefix + title)

        # 4. Info Line
        iy = top_y - 35*mm
        c.setFont(FONT_NAME, 10); c.drawString(margin, iy, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['s_t']}")
        c.drawRightString(width - margin, iy, f"เลขที่ : {run_no}")

        # 5. Customer & Doc Box
        ry = iy - 2*mm; rh = 25*mm; rbtm = ry - rh
        c.rect(margin, rbtm, width - 2*margin, rh)
        sx = width - margin - 60*mm; c.line(sx, ry, sx, rbtm)
        
        cx = margin + 2*mm; cy = ry - 4*mm
        c.drawString(cx, cy, f"ชื่อลูกค้า : {doc_data['c_n']}")
        c.drawString(cx, cy - 5*mm, f"Tax ID : {doc_data['c_t']}")
        c.drawString(cx, cy - 10*mm, f"ที่อยู่ : {doc_data['c_a'][:60]}")
        c.drawString(cx, cy - 14*mm, f"       {doc_data['c_a'][60:110]}")
        c.drawString(cx, cy - 19*mm, f"โทร : {doc_data['c_tel']}")
        
        dx = sx + 2*mm; dy = ry - 4*mm
        c.drawString(dx, dy, f"วันที่ : {date_str}"); c.drawString(dx, dy - 5*mm, "ผู้ขาย : -"); c.drawString(dx, dy - 10*mm, "เครดิต : สด")

        # 6. Table
        ty = rbtm - 2*mm; th = 60*mm; tbtm = ty - th
        c.rect(margin, tbtm, width - 2*margin, th)
        c.line(margin, ty - 6*mm, width - margin, ty - 6*mm)
        
        cols = [10*mm, 85*mm, 15*mm, 25*mm]
        xp = [margin + sum(cols[:i]) for i in range(len(cols)+1)]
        xt = width - margin
        
        c.line(xp[1], ty, xp[1], tbtm); c.line(xp[2], ty, xp[2], tbtm); c.line(xp[3], ty, xp[3], tbtm); c.line(xp[4], ty, xp[4], tbtm)
        
        hdrs = ["ลำดับ", "รายการสินค้า", "จำนวน", "หน่วยละ", "จำนวนเงิน"]
        c.drawCentredString((margin+xp[1])/2, ty - 4*mm, hdrs[0])
        c.drawCentredString((xp[1]+xp[2])/2, ty - 4*mm, hdrs[1])
        c.drawCentredString((xp[2]+xp[3])/2, ty - 4*mm, hdrs[2])
        c.drawCentredString((xp[3]+xp[4])/2, ty - 4*mm, hdrs[3])
        c.drawCentredString((xp[4]+xt)/2, ty - 4*mm, hdrs[4])
        
        curr_y = ty - 10*mm
        for i, item in enumerate(items, 1):
            if i > 10: break
            c.drawCentredString((margin+xp[1])/2, curr_y, str(i))
            c.drawString(xp[1]+1*mm, curr_y, item['name'][:45])
            c.drawRightString(xp[3]-1*mm, curr_y, f"{item['qty']:,.0f}")
            c.drawRightString(xp[4]-1*mm, curr_y, f"{item['price']:,.2f}")
            c.drawRightString(xt-1*mm, curr_y, f"{item['qty']*item['price']:,.2f}")
            curr_y -= 5*mm

        # 7. Footer
        fy = tbtm
        c.rect(xp[4], fy - 25*mm, xt - xp[4], 25*mm); c.rect(margin, fy - 25*mm, xp[4] - margin, 25*mm)
        
        lbls = ["รวมเงิน", "ส่วนลด", "มูลค่า", "VAT 7%", "สุทธิ"]
        vals = [total_raw, 0, pre_vat, vat_amt, grand_total]
        y_val = fy - 4*mm
        for l, v in zip(lbls, vals):
            c.drawRightString(xp[4]+23*mm, y_val, l)
            c.drawRightString(xt-1*mm, y_val, f"{v:,.2f}")
            y_val -= 4.5*mm
            
        c.drawString(margin+5*mm, fy - 20*mm, "ผู้รับเงิน ........................................")

    # Draw Top & Bottom
    if doc_type == "ABB":
        draw_form(height/2 + 5*mm, False)
    else:
        draw_form(height/2 + 5*mm, False)
        c.setDash(3, 3); c.line(5*mm, height/2, width-5*mm, height/2); c.setDash(1, 0)
        draw_form(0, True)
    
    c.save(); buffer.seek(0)
    # 🟢 ส่งคืน 2 ค่า: ไฟล์ PDF และ ยอดเงิน (แก้ NameError ตรงนี้!)
    return buffer, grand_total

# ==========================================
# 🖥️ 4. Main App
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['f_n','f_t','f_a','f_tel','s_n','s_t','s_a']:
    if k not in st.session_state: st.session_state[k] = ""

with st.sidebar:
    st.title("Admin V111")
    if not st.session_state.logged_in:
        if st.button("Login") and st.text_input("Pwd", type="password") == ADMIN_PASSWORD:
            st.session_state.logged_in = True; st.rerun()
        st.stop()
    else:
        if st.button("Logout"): st.session_state.logged_in = False; st.rerun()
        if st.button("Reload"): st.cache_data.clear(); st.rerun()

try:
    sh, ws_conf, conf, ws_q = load_live_data()
    item_df, cust_df = load_static_data()
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName",""); st.session_state.s_t = conf.get("TaxID",""); st.session_state.s_a = conf.get("Address","")
except: st.error("DB Error (Quota)"); st.stop()

st.title("🧾 Nami Invoice (V111 Bug Fixed)")
col1, col2 = st.columns([1.2, 1])

with col1:
    with st.expander("🏠 ร้านค้า & โลโก้"):
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

    st.session_state.f_n = st.text_input("ชื่อลูกค้า", st.session_state.f_n)
    st.session_state.f_t = st.text_input("Tax ID (ลูกค้า)", st.session_state.f_t)
    st.session_state.f_a = st.text_area("ที่อยู่ลูกค้า", st.session_state.f_a)
    st.session_state.f_tel = st.text_input("โทร", st.session_state.f_tel)
    if st.button("Clear"):
        for k in ['f_n','f_t','f_a','f_tel']: st.session_state[k] = ""
        st.rerun()

    st.divider()
    doc_type = st.radio("Type", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    run_no = st.text_input("Doc No", value=conf.get(run_key, "INV-000"))
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
            if not st.session_state.f_n: st.error("No Name"); st.stop()
            with st.spinner("Processing..."):
                # Gen PDF
                d_data = {'s_n': st.session_state.s_n, 's_t': st.session_state.s_t, 's_a': st.session_state.s_a,
                          'c_n': st.session_state.f_n, 'c_t': st.session_state.f_t, 'c_a': st.session_state.f_a, 'c_tel': st.session_state.f_tel}
                # 🟢 รับค่า 2 ตัวแปรตรงนี้ (Fixed NameError)
                pdf, grand = generate_pdf_v111(d_data, st.session_state.cart, doc_type, run_no, datetime.now().strftime("%d/%m/%Y"), vat_inc, logo_up)
                
                # Update Sheet
                try:
                    smart_request(sh.worksheet("SalesLog").append_row, [datetime.now().strftime("%Y-%m-%d"), grand])
                    # Update Run No
                    p = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if p:
                        nxt = f"{p.group(1)}{str(int(p.group(2))+1).zfill(len(p.group(2)))}"
                        t_cell = 'B5' if doc_type == "Full" else 'B6'
                        smart_request(ws_conf.update_acell, t_cell, nxt)
                    # Clear Queue
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
