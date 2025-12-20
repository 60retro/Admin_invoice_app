import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
from io import BytesIO
import requests, base64, json, re
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

# --- Config ---
st.set_page_config(page_title="Nami Web (V87 Clone)", layout="wide")
ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL จากข้อ 2
SHEET_NAME = "Invoice_Data"

try: pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf')); FONT_NAME = 'CustomFont'
except: FONT_NAME = 'Helvetica'

# --- Connection ---
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets: creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else: creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

# --- Caching Data (ป้องกัน Quota เต็ม) ---
@st.cache_data(ttl=60) # จำข้อมูลสินค้า/ลูกค้า 60 วินาที
def load_static_data():
    client = get_client(); sh = client.open(SHEET_NAME)
    try: items = pd.DataFrame(sh.worksheet("Items").get_all_records())
    except: items = pd.DataFrame(columns=['ItemName'])
    try: cust = pd.DataFrame(sh.worksheet("Customers").get_all_records())
    except: cust = pd.DataFrame(columns=['Name'])
    return items, cust

# --- PDF Generator (V87 Logic Clone) ---
def generate_pdf_v87(doc_data, items, doc_type, running_no):
    buffer = BytesIO(); c = canvas.Canvas(buffer, pagesize=A4); width, height = A4; half_height = height / 2
    date_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%d/%m/%Y")

    def wrap_text_lines(text, width_limit, font, size):
        c.setFont(font, size); lines = []; words = str(text).split(' '); curr = []
        for w in words:
            if pdfmetrics.stringWidth(' '.join(curr + [w]), font, size) <= width_limit: curr.append(w)
            else:
                if curr: lines.append(' '.join(curr)); curr = [w]
                else: lines.append(w); curr = []
        if curr: lines.append(' '.join(curr))
        return lines

    def draw_invoice(y_offset):
        margin = 15 * mm; base_y = y_offset; top_y = base_y + half_height - margin
        font_std = 11; font_bold = 12; line_h = 12
        
        box_w = 260; box_h = 80; box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        c.setFont(FONT_NAME, font_bold); c.drawString(box_x + 10, box_y + box_h - 15, doc_data['shop_name'])
        c.setFont(FONT_NAME, font_std)
        raw_addr = doc_data['shop_addr'].split('\n'); cur_sy = box_y + box_h - 30
        for line in raw_addr:
            for w in wrap_text_lines(line, box_w - 20, FONT_NAME, font_std):
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w); cur_sy -= line_h

        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        title_y = box_y - 20; c.setFont(FONT_NAME, font_bold + 2); c.drawCentredString(margin + ((box_x - margin) / 2), title_y, f"ต้นฉบับ {title}")
        bar_y = title_y - 20; c.setFont(FONT_NAME, font_std)
        c.drawString(margin, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['shop_tax']}")
        c.drawRightString(width - margin, bar_y, f"เลขที่ : {running_no}")

        info_box_y = bar_y - 5; info_box_h = 75; info_box_btm = info_box_y - info_box_h
        c.rect(margin, info_box_btm, page_w, info_box_h); div_x = width - margin - 200; c.line(div_x, info_box_y, div_x, info_box_btm)
        
        cx = margin + 10; cy = info_box_y - 12; label_anchor = cx + 110
        c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, cy, "เลขประจำตัวผู้เสียภาษีอากร :")
        c.setFont(FONT_NAME, font_std); c.drawString(label_anchor + 5, cy, doc_data['cust_tax'])
        curr_y = cy - 12; c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, curr_y, "ชื่อลูกค้า :")
        c.setFont(FONT_NAME, font_std); avail_w = div_x - (label_anchor + 5) - 5
        for l in wrap_text_lines(doc_data['cust_name'], avail_w, FONT_NAME, font_std): c.drawString(label_anchor + 5, curr_y, l); curr_y -= 10
        curr_y -= 2; c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, curr_y, "ที่อยู่ :")
        c.setFont(FONT_NAME, font_std)
        # V87 Logic: Manual Wrap for Address (Correct Width Calculation)
        avail_w_addr = div_x - (label_anchor + 5) - 5
        for l in wrap_text_lines(doc_data['cust_addr'], avail_w_addr, FONT_NAME, font_std): c.drawString(label_anchor + 5, curr_y, l); curr_y -= 10
        
        tel_y = info_box_btm + 5; c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, tel_y, "โทรศัพท์ :")
        c.setFont(FONT_NAME, font_std); c.drawString(label_anchor + 5, tel_y, doc_data['cust_tel'])

        dx = div_x + 10; dy = info_box_y - 12; c.setFont(FONT_NAME, font_bold)
        c.drawRightString(dx + 80, dy, "วันที่เอกสาร :"); c.drawRightString(dx + 80, dy - 12, "พนักงานขาย :"); c.drawRightString(dx + 80, dy - 24, "เงื่อนไขการชำระ :")
        c.setFont(FONT_NAME, font_std); c.drawString(dx + 85, dy, date_str); c.drawString(dx + 85, dy - 24, "สด")

        tbl_top = info_box_btm - 5; c.setFillColorRGB(0.2, 0.2, 0.2); c.rect(margin, tbl_top - 14, page_w, 14, fill=1, stroke=1); c.setFillColorRGB(1, 1, 1)
        col_w = [25, page_w - 215, 45, 70, 75]; col_x = [margin, margin+col_w[0], margin+col_w[0]+col_w[1], margin+col_w[0]+col_w[1]+col_w[2], margin+col_w[0]+col_w[1]+col_w[2]+col_w[3]]
        c.setFont(FONT_NAME, font_bold)
        for i, h in enumerate(["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]): c.drawCentredString(col_x[i] + col_w[i]/2, tbl_top - 10, h)
        c.setFillColorRGB(0, 0, 0); curr_y = tbl_top - 14; c.setFont(FONT_NAME, font_std)
        total = 0
        for idx, item in enumerate(items, start=1):
            if idx > 15: break
            nm = item['name']; qty = item['qty']; pr = item['price']; amt = qty * pr; total += amt
            nm_lines = wrap_text_lines(str(nm), col_w[1] - 10, FONT_NAME, font_std)
            if len(nm_lines) > 3: nm_lines = nm_lines[:3]
            txt_y = curr_y - 12; c.drawCentredString(col_x[0] + col_w[0]/2, txt_y, str(idx))
            for i, l in enumerate(nm_lines): c.drawString(col_x[1] + 5, txt_y - (i * 12), l)
            c.drawRightString(col_x[2] + col_w[2] - 10, txt_y, f"{qty:,.0f}"); c.drawRightString(col_x[3] + col_w[3] - 5, txt_y, f"{pr:,.2f}"); c.drawRightString(col_x[4] + col_w[4] - 5, txt_y, f"{amt:,.2f}")
            curr_y -= 45; c.setLineWidth(0.5); c.line(margin, curr_y, width - margin, curr_y)

        btm = curr_y; c.rect(margin, btm, page_w, (tbl_top - 14) - btm)
        for x in col_x[1:]: c.line(x, tbl_top - 14, x, btm)
        vat = total * 7 / 107; pre = total - vat
        vals = [f"{total:,.2f}", "-", f"{pre:,.2f}", f"{vat:,.2f}", f"{total:,.2f}"]
        lbls = ["จำนวนเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        f_top = btm; row_h = 14; c.line(col_x[4], f_top, col_x[4], f_top - (5 * row_h)); c.line(width - margin, f_top, width - margin, f_top - (5 * row_h))
        for i in range(5):
            r_top = f_top - (i * row_h); r_btm = r_top - row_h; t_y = r_btm + 4; c.line(col_x[4], r_btm, width - margin, r_btm); c.setFont(FONT_NAME, font_std); c.drawRightString(col_x[4] - 15, t_y, lbls[i] + " :")
            if i == 4: c.setFont(FONT_NAME, font_bold); c.drawRightString(width - margin - 5, t_y, vals[i])
            else: c.drawRightString(width - margin - 5, t_y, vals[i])
        sig_y = f_top - (5 * row_h) - 25; c.setFont(FONT_NAME, font_std); c.drawString(margin + 20, sig_y, "ผู้รับสินค้า ..........................................................."); c.drawString(width - margin - 220, sig_y, "ผู้รับเงิน ...........................................................")

    if doc_type == "ABB": draw_invoice(half_height)
    else: draw_invoice(half_height); c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0); draw_invoice(0)
    c.save(); buffer.seek(0); return buffer

# --- Main App ---
if 'cart' not in st.session_state: st.session_state.cart = []
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
for k in ['f_n', 'f_t', 'f_a', 'f_tel', 'shop_n', 'shop_t', 'shop_a']: 
    if k not in st.session_state: st.session_state[k] = ""

if not st.session_state.logged_in:
    pwd = st.text_input("Admin Password", type="password")
    if st.button("Login") and pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
    st.stop()

# Load Cached Data
item_df, cust_df = load_static_data()

# Load Live Data (Config & Queue)
try:
    client = get_client(); sh = client.open(SHEET_NAME)
    ws_conf = sh.worksheet("Config"); conf = dict(ws_conf.get_all_values())
    # Sync Shop Info to State (First Time)
    if not st.session_state.shop_n:
        st.session_state.shop_n = conf.get("ShopName",""); st.session_state.shop_t = conf.get("TaxID",""); st.session_state.shop_a = conf.get("Address","")
except: st.error("Database Error"); st.stop()

# Sidebar
with st.sidebar:
    st.header("☁️ Queue"); 
    if st.button("Refresh"): load_static_data.clear(); st.rerun()
    try:
        q_df = pd.DataFrame(sh.worksheet("Queue").get_all_records())
        pending = q_df[q_df['Status'] != 'Done']
        for i, r in pending.iterrows():
            st.warning(f"{r['Name']} ({r['Price']})")
            if st.button("ดึงข้อมูล", key=f"p_{i}"):
                st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
                st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
                st.session_state.queue_idx = i + 2
                if r['Item']: st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": float(str(r['Price']).replace(',',''))}]
                st.rerun()
    except: pass

st.title("🧾 Nami Web (Hybrid System)")
c1, c2 = st.columns([1, 1.5])

with c1:
    with st.expander("🏠 ข้อมูลร้าน", expanded=True):
        st.session_state.shop_n = st.text_input("Shop Name", st.session_state.shop_n)
        st.session_state.shop_t = st.text_input("Shop Tax", st.session_state.shop_t)
        st.session_state.shop_a = st.text_area("Shop Address", st.session_state.shop_a)

    sel_cust = st.selectbox("🔍 ลูกค้าเก่า", [""] + list(cust_df['Name'].unique()))
    if sel_cust and sel_cust != st.session_state.get('last_cust'):
        r = cust_df[cust_df['Name'] == sel_cust].iloc[0]
        st.session_state.f_n = r['Name']; st.session_state.f_t = str(r['TaxID'])
        st.session_state.f_a = f"{r['Address1']} {r['Address2']}"; st.session_state.f_tel = str(r['Phone'])
        st.session_state.last_cust = sel_cust; st.rerun()

    st.session_state.f_n = st.text_input("ลูกค้า", st.session_state.f_n)
    st.session_state.f_t = st.text_input("Tax ID", st.session_state.f_t)
    st.session_state.f_a = st.text_area("ที่อยู่", st.session_state.f_a)
    st.session_state.f_tel = st.text_input("โทร", st.session_state.f_tel)
    
    doc_type = st.radio("Type", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    current_run = conf.get(run_key, "INV-000")
    run_no = st.text_input("เลขที่เอกสาร", value=current_run)

with c2:
    sel_item = st.selectbox("สินค้า", [""] + list(item_df['ItemName'].unique()))
    qty = st.number_input("จำนวน", 1); price = st.number_input("ราคา", 0.0)
    if st.button("เพิ่ม") and sel_item: st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        cdf = pd.DataFrame(st.session_state.cart); cdf['Total'] = cdf['qty']*cdf['price']
        st.dataframe(cdf, use_container_width=True)
        if st.button("Clear Cart"): st.session_state.cart = []; st.rerun()
        
        if st.button("🖨️ Save & Generate PDF", type="primary"):
            # 1. Update Sheet (DB Sync)
            try:
                # Update Running No
                prefix = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                next_run = f"{prefix.group(1)}{str(int(prefix.group(2))+1).zfill(len(prefix.group(2)))}" if prefix else run_no
                ws_conf.update_cell(ws_conf.find(run_key).row, 2, next_run)
                
                # Sales Log
                try: sh.worksheet("SalesLog").append_row([datetime.now().strftime("%Y-%m-%d"), run_no, st.session_state.f_n, cdf['Total'].sum(), doc_type, "Web"])
                except: pass
                
                # Queue Status
                if st.session_state.get('queue_idx'): sh.worksheet("Queue").update_cell(st.session_state.queue_idx, 10, "Done")
            except Exception as e: st.error(f"Sync Error: {e}")

            # 2. Gen PDF
            info = {"shop_name": st.session_state.shop_n, "shop_tax": st.session_state.shop_t, "shop_addr": st.session_state.shop_a,
                    "cust_name": st.session_state.f_n, "cust_tax": st.session_state.f_t, "cust_addr": st.session_state.f_a, "cust_tel": st.session_state.f_tel}
            pdf = generate_pdf_v87(info, st.session_state.cart, doc_type, run_no)
            fname = f"INV_{run_no}.pdf"
            
            # 3. Backup
            try: 
                r = requests.post(APPS_SCRIPT_URL, json={"filename": fname, "file": base64.b64encode(pdf.getvalue()).decode('utf-8')})
                st.success("✅ Backup Success")
            except: st.warning("⚠️ Backup Failed")
            
            st.download_button("Download PDF", pdf, fname, "application/pdf")
