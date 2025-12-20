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
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import ParagraphStyle
import re
import time

# ==========================================
# ⚙️ 1. ตั้งค่าระบบ
# ==========================================
st.set_page_config(page_title="Nami Admin V104", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 อย่าลืมใส่ URL เดิม
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"
SHEET_NAME = "Invoice_Data"

try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except: FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. เชื่อมต่อ Google Services (Strong Cache)
# ==========================================
@st.cache_resource
def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        return ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else: return ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

@st.cache_resource
def get_sheet_client():
    return gspread.authorize(get_credentials())

@st.cache_data(ttl=600) # Cache นาน 10 นาที เพื่อลด Quota
def load_static_data():
    try:
        client = get_sheet_client()
        sh = client.open(SHEET_NAME)
        
        # Load Items (Safe Mode)
        try: 
            item_data = sh.worksheet("Items").get_all_records()
            item_df = pd.DataFrame(item_data) if item_data else pd.DataFrame(columns=['ItemName'])
        except: item_df = pd.DataFrame(columns=['ItemName'])
        
        # Load Customers (Safe Mode)
        try: 
            cust_data = sh.worksheet("Customers").get_all_records()
            cust_df = pd.DataFrame(cust_data) if cust_data else pd.DataFrame(columns=['Name'])
        except: cust_df = pd.DataFrame(columns=['Name'])
        
        return item_df, cust_df
    except:
        return pd.DataFrame(), pd.DataFrame() # คืนค่าว่างถ้าพัง

# ดึงข้อมูลสด (Config/Queue) แยกต่างหาก
def get_live_data():
    client = get_sheet_client()
    sh = client.open(SHEET_NAME)
    ws_conf = sh.worksheet("Config")
    # อ่านแบบ Safe list
    raw = ws_conf.get_all_values()
    conf = {}
    for r in raw:
        if len(r) >= 2: conf[str(r[0]).strip()] = str(r[1]).strip()
    
    ws_q = sh.worksheet("Queue")
    return sh, ws_conf, conf, ws_q

# ==========================================
# 🛠️ 3. Helper Functions
# ==========================================
def smart_clean_address(addr1, addr2):
    house = str(addr1); dist = ""; prov = str(addr2)
    match_amp = re.search(r'(เขต|อำเภอ|อ\.)\s*([^\s]+)', prov)
    if match_amp:
        extracted = match_amp.group(0); dist += extracted + " "; prov = prov.replace(extracted, "").strip()
    match_tum = re.search(r'(แขวง|ตำบล|ต\.)\s*([^\s]+)', house)
    if match_tum:
        extracted = match_tum.group(0); dist = extracted + " " + dist; house = house.replace(extracted, "").strip()
    return house.strip(), dist.strip(), prov.strip()

def upload_via_script(file_obj, filename):
    try:
        file_obj.seek(0)
        file_content = base64.b64encode(file_obj.read()).decode('utf-8')
        payload = {"filename": filename, "mimeType": "application/pdf", "file": file_content, "folderId": DRIVE_FOLDER_ID}
        response = requests.post(APPS_SCRIPT_URL, json=payload)
        res_json = response.json()
        if res_json.get("status") == "success": return True, res_json.get("fileId")
        else: return False, res_json.get("message")
    except Exception as e: return False, str(e)

# ==========================================
# 🖨️ 4. PDF Engine (V90 Logic)
# ==========================================
def generate_pdf_v90(doc_data, items, doc_type, running_no):
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
        page_w = width - (2 * margin); font_std = 11; font_bold = 12; line_h = 12
        
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
        style = ParagraphStyle('Normal', fontName=FONT_NAME, fontSize=11, leading=12)
        p = Paragraph(doc_data['cust_addr'], style)
        f_addr = Frame(label_anchor + 5, info_box_btm + 15, avail_w, (curr_y - info_box_btm) + 5, showBoundary=0, topPadding=0)
        f_addr.addFromList([p], c)
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
            if i == 4: c.setFont(FONT_NAME, font_bold)
            c.drawRightString(width - margin - 5, t_y, vals[i])
        sig_y = f_top - (5 * row_h) - 25; c.setFont(FONT_NAME, font_std); c.drawString(margin + 20, sig_y, "ผู้รับสินค้า ..........................................................."); c.drawString(width - margin - 220, sig_y, "ผู้รับเงิน ...........................................................")

    if doc_type == "ABB": draw_invoice(half_height)
    else: draw_invoice(half_height); c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0); draw_invoice(0)
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 5. Init State & Load Data (Cached)
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
if 'queue_idx' not in st.session_state: st.session_state.queue_idx = None
for k in ['form_name', 'form_tax', 'form_h', 'form_d', 'form_p', 'form_tel']:
    if k not in st.session_state: st.session_state[k] = ""

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔒 Admin Login")
        pwd = st.text_input("กรุณาใส่รหัสผ่าน", type="password")
        if st.button("เข้าสู่ระบบ"):
            if pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
            else: st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop()

# Load Cached Data
item_df, cust_df = load_static_data()

# Load Live Data (Config/Queue) - Safe Mode
try:
    sh, ws_conf, conf_data, ws_q = get_live_data()
    seller_info = {"n": conf_data.get("ShopName", "Nami"), "t": conf_data.get("TaxID", ""), "a": conf_data.get("Address", "")}
except Exception as e:
    st.error(f"เชื่อมต่อ Google Sheet ไม่ได้ (Quota เต็ม?): {e}")
    st.stop()

# ==========================================
# ⚡️ 6. Logic Processing
# ==========================================
with st.sidebar:
    st.header("☁️ รายการรอคิว")
    if st.button("🔄 รีเฟรชข้อมูล (ดึงใหม่)"): 
        load_static_data.clear() # Clear Cache
        st.rerun()
        
    try:
        q_data = ws_q.get_all_records()
        q_df = pd.DataFrame(q_data)
        if not q_df.empty and 'Status' in q_df.columns:
            pending = q_df[q_df['Status'] != 'Done']
            if not pending.empty:
                for idx, r in pending.iterrows():
                    st.warning(f"**{r['Name']}** ({r['Price']})")
                    if st.button("ดึงข้อมูล", key=f"pull_{idx}"):
                        h, d, p = smart_clean_address(r['Address1'], r['Address2'])
                        st.session_state.form_name = r['Name']
                        st.session_state.form_tax = str(r['TaxID'])
                        st.session_state.form_h = h; st.session_state.form_d = d; st.session_state.form_p = p; st.session_state.form_tel = str(r['Phone'])
                        st.session_state.queue_idx = idx + 2
                        if r['Item']:
                            st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": float(str(r['Price']).replace(',',''))}]
                        st.rerun()
            else: st.success("ไม่มีคิวค้าง")
    except Exception as e: st.warning("ยังโหลดคิวไม่ได้ (รอสักครู่)")

# ==========================================
# 🖥️ 7. Layout & Form
# ==========================================
st.title("🧾 Nami Invoice (V104 Safe Mode)")
col_L, col_R = st.columns([1, 1.5])

with col_L:
    with st.expander("🔒 ข้อมูลผู้ขาย (Admin)", expanded=False):
        st.text_input("ชื่อร้าน", value=seller_info['n'], disabled=True)
        st.text_input("Tax ID", value=seller_info['t'], disabled=True)
        st.text_area("ที่อยู่", value=seller_info['a'], disabled=True, height=80)

    st.markdown("### 👤 ข้อมูลลูกค้า")
    # 🔴 FIX: ใช้ get() ป้องกัน KeyError ถ้า DataFrame ว่าง
    cust_options = [""] + list(cust_df['Name'].unique()) if 'Name' in cust_df.columns else [""]
    selected_cust = st.selectbox("🔍 ค้นหาลูกค้า (ชื่อ)", cust_options)
    
    if selected_cust and selected_cust != st.session_state.get('last_selected_cust'):
        row = cust_df[cust_df['Name'] == selected_cust].iloc[0]
        h, d, p = smart_clean_address(row['Address1'], row['Address2'])
        st.session_state.form_name = row['Name']; st.session_state.form_tax = str(row['TaxID']); st.session_state.form_h = h
        st.session_state.form_d = d; st.session_state.form_p = p; st.session_state.form_tel = str(row['Phone'])
        st.session_state.last_selected_cust = selected_cust
        st.rerun()

    c_name = st.text_input("ชื่อลูกค้า", key="form_name")
    c_tax = st.text_input("เลขผู้เสียภาษี", key="form_tax")
    c_h = st.text_input("ที่อยู่ (เลขที่/ถนน)", key="form_h")
    cc1, cc2 = st.columns(2)
    c_d = cc1.text_input("ตำบล/อำเภอ", key="form_d")
    c_p = cc2.text_input("จังหวัด/รหัส", key="form_p")
    c_tel = st.text_input("เบอร์โทร", key="form_tel")

    st.markdown("---"); st.markdown("### 📄 ตั้งค่าเอกสาร")
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    current_run = conf_data.get(run_key, "INV-000")
    st.info(f"เลขที่เอกสารปัจจุบัน: **{current_run}**")

with col_R:
    st.markdown("### 🛒 รายการสินค้า")
    ic1, ic2, ic3, ic4 = st.columns([3, 1, 1, 1])
    # 🔴 FIX: ป้องกัน KeyError ถ้า DataFrame ว่าง
    item_options = [""] + list(item_df['ItemName'].unique()) if 'ItemName' in item_df.columns else [""]
    with ic1: sel_item = st.selectbox("เลือกสินค้า", item_options)
    with ic2: qty = st.number_input("จำนวน", min_value=1, value=1)
    with ic3: price = st.number_input("ราคา", min_value=0.0, value=0.0)
    with ic4:
        st.write(""); st.write("")
        if st.button("➕ เพิ่ม") and sel_item: st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        cart_df = pd.DataFrame(st.session_state.cart)
        cart_df['Total'] = cart_df['qty'] * cart_df['price']
        st.dataframe(cart_df, use_container_width=True)
        if st.button("ลบรายการล่าสุด", type="secondary"): st.session_state.cart.pop(); st.rerun()
        grand_total = cart_df['Total'].sum()
        st.markdown(f"### 💰 ยอดรวม: `{grand_total:,.2f}` บาท")
        st.markdown("---")
        
        use_backup = st.checkbox("Backup ลง Google Drive", value=True)

        if st.button("🖨️ ยืนยันออกบิล (Confirm & Save)", type="primary", use_container_width=True):
            if not c_name: st.error("กรุณาระบุชื่อลูกค้า")
            else:
                with st.spinner("กำลังบันทึกข้อมูล..."):
                    try:
                        # Config
                        new_run = current_run
                        try:
                            match = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", current_run)
                            if match:
                                prefix, num_str = match.groups()
                                new_run = f"{prefix}{str(int(num_str)+1).zfill(len(num_str))}"
                            else: new_run = f"INV-{datetime.now().strftime('%y%m')}-001"
                        except: new_run = "INV-ERROR-001"

                        cell = ws_conf.find(run_key); ws_conf.update_cell(cell.row, 2, new_run)
                        
                        try:
                            ws_log = sh.worksheet("SalesLog")
                            ws_log.append_row([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), grand_total])
                        except: pass

                        if st.session_state.queue_idx:
                            ws_q.update_cell(st.session_state.queue_idx, 10, "Done") 
                            st.session_state.queue_idx = None
                    except Exception as e: st.error(f"Sheet Update Warning (Quota?): {e}")

                    doc_data = {"shop_name": seller_info['n'], "shop_tax": seller_info['t'], "shop_addr": seller_info['a'], "cust_name": c_name, "cust_tax": c_tax, "cust_tel": c_tel, "cust_addr": f"{c_h} {c_d} {c_p}".strip()}
                    pdf_buffer = generate_pdf_v90(doc_data, st.session_state.cart, doc_type, current_run)
                    fname = f"INV_{c_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    
                    backup_msg = ""
                    if use_backup:
                        ok, res = upload_via_script(pdf_buffer, fname)
                        backup_msg = f"✅ Backup สำเร็จ" if ok else f"⚠️ Backup ไม่ผ่าน: {res}"
                    
                    st.success(f"✅ บันทึกยอดขายแล้ว! {backup_msg}")
                    st.download_button("⬇️ ดาวน์โหลด PDF", data=pdf_buffer, file_name=fname, mime="application/pdf")
                    
                    st.session_state.cart = []
                    for k in ['form_name', 'form_tax', 'form_h', 'form_d', 'form_p', 'form_tel']: st.session_state[k] = ""
    else: st.info("ยังไม่มีสินค้าในตะกร้า")
