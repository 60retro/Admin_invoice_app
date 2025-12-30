import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build 
from googleapiclient.http import MediaIoBaseDownload 
import pandas as pd
from datetime import datetime
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
# ⚙️ 1. Config & Language
# ==========================================
st.set_page_config(page_title="Nami Admin V120", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec"
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur"
LOGO_FILE_ID = "1nftUz6Y_deqC2lrNw68KRKgxArRIE0dy" 

# --- DATABASE ภาษา (เหมือน Desktop V119) ---
LANG_DB = {
    "TH": {
        "ui_shop": "🏠 ข้อมูลร้านค้า", "ui_cust": "👤 ข้อมูลลูกค้า", "ui_doc": "📄 ตั้งค่าเอกสาร", "ui_item": "🛒 สินค้า",
        "lbl_shop": "ชื่อร้าน", "lbl_tax": "Tax ID", "lbl_addr": "ที่อยู่", "btn_save_shop": "บันทึกร้าน",
        "lbl_c_name": "ชื่อลูกค้า", "lbl_c_tax": "Tax ID (ลูกค้า)", "lbl_c_addr": "ที่อยู่", "lbl_c_tel": "เบอร์โทร",
        "btn_clear": "🧹 ล้างค่า", "lbl_doc_no": "เลขที่เอกสาร", "lbl_date": "วันที่", "chk_vat": "ราคารวม VAT แล้ว",
        "col_qty": "จำนวน", "col_price": "ราคา", "btn_add": "➕ เพิ่ม", "btn_del": "ลบรายการล่าสุด",
        "btn_print": "🖨️ พิมพ์ PDF & บันทึก", "msg_saved": "บันทึกเรียบร้อย", "msg_no_name": "กรุณาระบุชื่อลูกค้า",
        "p_orig": "ต้นฉบับ", "p_copy": "สำเนา", "p_title_full": "ใบกำกับภาษี / ใบเสร็จรับเงิน", "p_title_abb": "ใบกำกับภาษีอย่างย่อ (ABB)",
        "p_taxid": "เลขประจำตัวผู้เสียภาษีอากร", "p_no": "เลขที่", "p_date": "วันที่เอกสาร",
        "p_cust_name": "ชื่อลูกค้า", "p_cust_addr": "ที่อยู่", "p_cust_tel": "โทรศัพท์",
        "p_sales": "พนักงานขาย", "p_cond": "เงื่อนไขการชำระ", "p_cash": "สด",
        "p_no_col": "ลำดับ", "p_item_col": "รายการสินค้า", "p_qty_col": "จำนวน", "p_uprice_col": "ราคาต่อหน่วย", "p_total_col": "จำนวนเงิน",
        "p_sum": "จำนวนเงิน", "p_disc": "ส่วนลด", "p_before_vat": "ราคาสินค้า/บริการ", "p_vat": "ภาษีมูลค่าเพิ่ม 7%", "p_grand": "จำนวนเงินรวมทั้งสิ้น",
        "p_sig_recv": "ผู้รับสินค้า", "p_sig_pay": "ผู้รับเงิน"
    },
    "EN": {
        "ui_shop": "🏠 Shop Info", "ui_cust": "👤 Customer", "ui_doc": "📄 Document", "ui_item": "🛒 Items",
        "lbl_shop": "Name", "lbl_tax": "Tax ID", "lbl_addr": "Address", "btn_save_shop": "Save Shop",
        "lbl_c_name": "Name", "lbl_c_tax": "Tax ID", "lbl_c_addr": "Address", "lbl_c_tel": "Phone",
        "btn_clear": "🧹 Clear", "lbl_doc_no": "Doc No", "lbl_date": "Date", "chk_vat": "VAT Included",
        "col_qty": "Qty", "col_price": "Price", "btn_add": "➕ Add", "btn_del": "Remove Last",
        "btn_print": "🖨️ Print & Save", "msg_saved": "Saved!", "msg_no_name": "Customer Name Required",
        "p_orig": "Original", "p_copy": "Copy", "p_title_full": "Tax Invoice / Receipt", "p_title_abb": "Abbreviated Tax Invoice",
        "p_taxid": "Tax ID", "p_no": "No", "p_date": "Date",
        "p_cust_name": "Customer", "p_cust_addr": "Address", "p_cust_tel": "Tel",
        "p_sales": "Salesperson", "p_cond": "Term", "p_cash": "Cash",
        "p_no_col": "No.", "p_item_col": "Description", "p_qty_col": "Qty", "p_uprice_col": "Unit Price", "p_total_col": "Amount",
        "p_sum": "Subtotal", "p_disc": "Discount", "p_before_vat": "Pre-VAT", "p_vat": "VAT 7%", "p_grand": "Grand Total",
        "p_sig_recv": "Received By", "p_sig_pay": "Authorized By"
    },
    "MM": {
        "ui_shop": "🏠 ဆိုင်အချက်အလက်", "ui_cust": "👤 ဝယ်သူ", "ui_doc": "📄 စာရွက်စာတမ်း", "ui_item": "🛒 ပစ္စည်း",
        "lbl_shop": "ဆိုင်အမည်", "lbl_tax": "အခွန်နံပါတ်", "lbl_addr": "လိပ်စာ", "btn_save_shop": "သိမ်းဆည်းမည်",
        "lbl_c_name": "အမည်", "lbl_c_tax": "အခွန်", "lbl_c_addr": "လိပ်စာ", "lbl_c_tel": "ဖုန်း",
        "btn_clear": "🧹 ရှင်းမည်", "lbl_doc_no": "နံပါတ်", "lbl_date": "ရက်စွဲ", "chk_vat": "VAT ပါပြီး",
        "col_qty": "အရေအတွက်", "col_price": "စျေးနှုန်း", "btn_add": "➕ ထည့်မည်", "btn_del": "ဖျက်မည်",
        "btn_print": "🖨️ ထုတ်မည် & သိမ်းမည်", "msg_saved": "သိမ်းဆည်းပြီး", "msg_no_name": "အမည်ထည့်ပါ",
        "p_orig": "မူရင်း", "p_copy": "မိတ္တူ", "p_title_full": "အခွန်ဘောက်ချာ / ပြေစာ", "p_title_abb": "အခွန်ဘောက်ချာ (အကျဉ်း)",
        "p_taxid": "အခွန်နံပါတ်", "p_no": "အမှတ်", "p_date": "ရက်စွဲ",
        "p_cust_name": "ဝယ်ယူသူအမည်", "p_cust_addr": "လိပ်စာ", "p_cust_tel": "ဖုန်း",
        "p_sales": "အရောင်းဝန်ထမ်း", "p_cond": "ငွေပေးချေမှု", "p_cash": "ငွေသား",
        "p_no_col": "စဉ်", "p_item_col": "ပစ္စည်းအမျိုးအစား", "p_qty_col": "အရေအတွက်", "p_uprice_col": "စျေးနှုန်း", "p_total_col": "သင့်ငွေ",
        "p_sum": "စုစုပေါင်း", "p_disc": "လျှော့စျေး", "p_before_vat": "အခွန်မပါစျေး", "p_vat": "VAT 7%", "p_grand": "စုစုပေါင်းငွေ",
        "p_sig_recv": "ပစ္စည်းလက်ခံသူ", "p_sig_pay": "ငွေလက်ခံသူ"
    }
}

try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except: FONT_NAME = 'Helvetica'

# ==========================================
# 🔌 2. Connection & Logic
# ==========================================
@st.cache_resource
def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        return ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else: return ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

@st.cache_resource
def get_gspread_client(): return gspread.authorize(get_credentials())

@st.cache_resource
def get_drive_service(): return build('drive', 'v3', credentials=get_credentials())

def smart_request(func, *args):
    for i in range(3):
        try: return func(*args)
        except Exception as e:
            if "429" in str(e) or "Quota" in str(e): time.sleep(2); continue
            raise e
    return func(*args)

@st.cache_data(ttl=3600)
def download_logo_from_drive(file_id):
    try:
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        file_stream = BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)
        done = False
        while done is False: status, done = downloader.next_chunk()
        file_stream.seek(0)
        return file_stream
    except: return None

@st.cache_data(ttl=300)
def load_static_data():
    try:
        client = get_gspread_client(); sh = client.open(SHEET_NAME)
        items = smart_request(lambda: pd.DataFrame(sh.worksheet("Items").get_all_records()))
        custs = smart_request(lambda: pd.DataFrame(sh.worksheet("Customers").get_all_records()))
        return items, custs
    except: return pd.DataFrame(), pd.DataFrame()

def load_live_data():
    client = get_gspread_client(); sh = client.open(SHEET_NAME)
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
# 🖨️ 3. PDF Generator (Desktop V119 Logic)
# ==========================================
def generate_pdf_multi_lang(doc_data, items, doc_type, run_no, date_str, vat_inc, logo_stream, lang_code):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4; half_height = height / 2
    
    # Load Language Dict
    txt = LANG_DB.get(lang_code, LANG_DB["TH"])

    total = sum([x['qty'] * x['price'] for x in items])
    if vat_inc: g=total; s=total/1.07; v=g-s
    else: s=total; v=total*0.07; g=s+v; g=math.floor(g)

    def wrap_text_lines(text, width_limit, font_name, font_size):
        c.setFont(font_name, font_size)
        words = str(text).split(' ')
        lines = []; current_line = []
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
        margin = 15 * mm; base_y = y_offset; top_y = base_y + half_height - margin
        page_w = width - (2 * margin)
        font_std = 11; font_bold = 12; line_h = 12
        
        # Logo
        logo_w = 110; logo_h = 55
        if logo_stream:
            try:
                logo_stream.seek(0)
                img = ImageReader(logo_stream)
                c.drawImage(img, margin, top_y - logo_h + 5, width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
            except: pass

        # Shop Box
        box_w = 260; box_h = 80; box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        c.setFont(FONT_NAME, font_bold); c.drawString(box_x + 10, box_y + box_h - 15, doc_data['s_n'])
        c.setFont(FONT_NAME, font_std)
        raw_addr = doc_data['s_a'].split('\n'); cur_sy = box_y + box_h - 30
        for line in raw_addr:
            wrapped = wrap_text_lines(line, box_w - 20, FONT_NAME, font_std)
            for w in wrapped:
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w); cur_sy -= line_h

        # Title (Dynamic Lang)
        t_str = txt['p_title_full'] if doc_type == "Full" else txt['p_title_abb']
        prefix = txt['p_orig'] if y_offset > 0 else txt['p_copy']
        if doc_type == "ABB": prefix = ""
        full_title = f"{prefix} {t_str}".strip()

        title_y = box_y - 20
        c.setFont(FONT_NAME, font_bold + 2); center_x_left = margin + ((box_x - margin) / 2)
        c.drawCentredString(center_x_left, title_y, full_title)
        
        bar_y = title_y - 20
        c.setFont(FONT_NAME, font_std)
        c.drawString(margin, bar_y, f"{txt['p_taxid']} : {doc_data['s_t']}")
        c.drawRightString(width - margin, bar_y, f"{txt['p_no']} : {run_no}")

        # Info Box
        info_box_y = bar_y - 5; info_box_h = 75; info_box_btm = info_box_y - info_box_h
        c.rect(margin, info_box_btm, page_w, info_box_h)
        div_x = width - margin - 200
        c.line(div_x, info_box_y, div_x, info_box_btm)
        
        cx = margin + 10; cy = info_box_y - 12; label_anchor = cx + 110
        c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, cy, f"{txt['p_taxid']} :"); c.setFont(FONT_NAME, font_std)
        c.drawString(label_anchor + 5, cy, doc_data['c_t'])
        cy -= 12
        c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, cy, f"{txt['p_cust_name']} :"); c.setFont(FONT_NAME, font_std)
        avail_w = div_x - (label_anchor + 5) - 5
        for l in wrap_text_lines(doc_data['c_n'], avail_w, FONT_NAME, font_std): c.drawString(label_anchor + 5, cy, l); cy -= 10
        cy -= 2
        c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, cy, f"{txt['p_cust_addr']} :"); c.setFont(FONT_NAME, font_std)
        for l in wrap_text_lines(doc_data['c_a'], avail_w, FONT_NAME, font_std): c.drawString(label_anchor + 5, cy, l); cy -= 10
        tel_y = info_box_btm + 5
        c.setFont(FONT_NAME, font_bold); c.drawRightString(label_anchor, tel_y, f"{txt['p_cust_tel']} :"); c.setFont(FONT_NAME, font_std); c.drawString(label_anchor + 5, tel_y, doc_data['c_tel'])

        dx = div_x + 10; dy = info_box_y - 12
        c.setFont(FONT_NAME, font_bold)
        c.drawRightString(dx + 80, dy, f"{txt['p_date']} :"); c.drawRightString(dx + 80, dy - 12, f"{txt['p_sales']} :"); c.drawRightString(dx + 80, dy - 24, f"{txt['p_cond']} :")
        c.setFont(FONT_NAME, font_std)
        c.drawString(dx + 85, dy, date_str); c.drawString(dx + 85, dy - 24, txt['p_cash'])

        # Table
        tbl_top = info_box_btm - 5
        c.setFillColorRGB(0.2, 0.2, 0.2); c.rect(margin, tbl_top - 14, page_w, 14, fill=1, stroke=1); c.setFillColorRGB(1, 1, 1)
        col_w = [25, page_w - 215, 45, 70, 75]
        col_x = [margin, margin+col_w[0], margin+col_w[0]+col_w[1], margin+col_w[0]+col_w[1]+col_w[2], margin+col_w[0]+col_w[1]+col_w[2]+col_w[3]]
        
        c.setFont(FONT_NAME, font_bold)
        headers = [txt['p_no_col'], txt['p_item_col'], txt['p_qty_col'], txt['p_uprice_col'], txt['p_total_col']]
        for i, h in enumerate(headers): c.drawCentredString(col_x[i] + col_w[i]/2, tbl_top - 10, h)
        c.setFillColorRGB(0, 0, 0)
        
        current_y = tbl_top - 14; c.setFont(FONT_NAME, font_std)
        for idx, item in enumerate(items, start=1):
            if idx > 15: break
            nm_lines = wrap_text_lines(str(item['name']), col_w[1] - 10, FONT_NAME, font_std)
            if len(nm_lines) > 3: nm_lines = nm_lines[:3]
            txt_y = current_y - 12
            c.drawCentredString(col_x[0] + col_w[0]/2, txt_y, str(idx))
            for i, l in enumerate(nm_lines): c.drawString(col_x[1] + 5, txt_y - (i*12), l)
            c.drawRightString(col_x[2] + col_w[2] - 10, txt_y, f"{item['qty']:,.0f}")
            c.drawRightString(col_x[3] + col_w[3] - 5, txt_y, f"{item['price']:,.2f}")
            c.drawRightString(col_x[4] + col_w[4] - 5, txt_y, f"{item['qty']*item['price']:,.2f}")
            current_y -= 45
            c.setLineWidth(0.5); c.line(margin, current_y, width - margin, current_y)
            
        btm = current_y
        c.rect(margin, btm, page_w, (tbl_top - 14) - btm)
        for x in col_x[1:]: c.line(x, tbl_top - 14, x, btm)
        
        # Footer
        f_top = btm; row_h = 14
        lbls = [txt['p_sum'], txt['p_disc'], txt['p_before_vat'], txt['p_vat'], txt['p_grand']]
        vals = [f"{s+v:,.2f}", "-", f"{s:,.2f}", f"{v:,.2f}", f"{g:,.2f}"]
        c.line(col_x[4], f_top, col_x[4], f_top - (5 * row_h)); c.line(width - margin, f_top, width - margin, f_top - (5 * row_h))
        for i in range(5):
            r_top = f_top - (i * row_h); r_btm = r_top - row_h; t_y = r_btm + 4
            c.line(col_x[4], r_btm, width - margin, r_btm)
            c.setFont(FONT_NAME, font_std); c.drawRightString(col_x[4] - 15, t_y, lbls[i] + " :")
            if i == 4: c.setFont(FONT_NAME, font_bold)
            c.drawRightString(width - margin - 5, t_y, vals[i])
            
        sig_y = f_top - (5 * row_h) - 25
        c.setFont(FONT_NAME, font_std)
        c.drawString(margin + 20, sig_y, f"{txt['p_sig_recv']} ...........................................................")
        c.drawString(width - margin - 220, sig_y, f"{txt['p_sig_pay']} ...........................................................")

    if doc_type == "ABB": draw_invoice(half_height)
    else:
        draw_invoice(half_height); c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0)
        draw_invoice(0)
    c.save(); buffer.seek(0)
    return buffer, g

# ==========================================
# 🖥️ 4. UI Logic
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['s_n', 's_t', 's_a', 'c_n', 'c_t', 'c_a1', 'c_a2', 'c_tel']:
    if k not in st.session_state: st.session_state[k] = ""

# Load Language
if 'ui_lang' not in st.session_state: st.session_state.ui_lang = "TH"
L = LANG_DB[st.session_state.ui_lang]

# Sidebar
with st.sidebar:
    st.title("Menu")
    # Language Selector
    st.session_state.ui_lang = st.selectbox("Language / ภาษา / ဘာသာစကား", ["TH", "EN", "MM"])
    st.divider()
    
    if not st.session_state.logged_in:
        if st.button("Login") and st.text_input("Pwd", type="password") == ADMIN_PASSWORD:
            st.session_state.logged_in = True; st.rerun()
        st.stop()
    else:
        if st.button("Logout"): st.session_state.logged_in = False; st.rerun()
        if st.button("🔄 Sync DB"): st.cache_data.clear(); st.rerun()

# Auto-Download Logo
logo_io = download_logo_from_drive(LOGO_FILE_ID)

try:
    sh, ws_conf, conf, ws_q = load_live_data()
    item_df, cust_df = load_static_data()
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName",""); st.session_state.s_t = conf.get("TaxID",""); st.session_state.s_a = conf.get("Address","")
except: st.error("DB Error (Quota)"); st.stop()

# --- Main Page ---
st.title(f"🧾 Nami Admin ({st.session_state.ui_lang})")
col1, col2 = st.columns([1.2, 1])

with col1:
    with st.expander(L['ui_shop'], expanded=True):
        st.session_state.s_n = st.text_input(L['lbl_shop'], st.session_state.s_n)
        st.session_state.s_t = st.text_input(L['lbl_tax'], st.session_state.s_t)
        st.session_state.s_a = st.text_area(L['lbl_addr'], st.session_state.s_a)
        
        if logo_io: st.image(logo_io, width=150)
        
        if st.button(L['btn_save_shop']):
            smart_request(ws_conf.update_acell, 'B2', st.session_state.s_n)
            smart_request(ws_conf.update_acell, 'B3', st.session_state.s_t)
            smart_request(ws_conf.update_acell, 'B4', st.session_state.s_a)
            st.success(L['msg_saved'])

    st.subheader(L['ui_cust'])
    cust_opts = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else []
    sel_c = st.selectbox("Search", cust_opts)
    if sel_c and sel_c != st.session_state.get('lc'):
        r = cust_df[cust_df['Name']==sel_c].iloc[0]
        st.session_state.c_n = r['Name']; st.session_state.c_t = str(r['TaxID'])
        st.session_state.c_a1 = r['Address1']; st.session_state.c_a2 = r['Address2']; st.session_state.c_tel = str(r['Phone'])
        st.session_state.lc = sel_c; st.rerun()

    st.session_state.c_n = st.text_input(L['lbl_c_name'], value=st.session_state.c_n)
    st.session_state.c_t = st.text_input(L['lbl_c_tax'], value=st.session_state.c_t)
    st.session_state.c_a = st.text_area(L['lbl_c_addr'], value=f"{st.session_state.c_a1} {st.session_state.c_a2}".strip())
    st.session_state.c_tel = st.text_input(L['lbl_c_tel'], value=st.session_state.c_tel)
    
    if st.button(L['btn_clear']):
        for k in ['c_n','c_t','c_a1','c_a2','c_tel']: st.session_state[k] = ""
        st.rerun()

    st.divider()
    doc_type = st.radio("Type", ["Full", "ABB"], horizontal=True)
    run_no = st.text_input(L['lbl_doc_no'], value=conf.get("Full_No" if doc_type=="Full" else "Abb_No", "INV-000"))
    vat_inc = st.checkbox(L['chk_vat'], value=True)

with col2:
    st.subheader(L['ui_item'])
    item_opts = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else []
    sel_i = st.selectbox("Item", item_opts)
    c_q, c_p, c_b = st.columns([1,1,1])
    q = c_q.number_input(L['col_qty'], 1); p = c_p.number_input(L['col_price'], 0.0)
    if c_b.button(L['btn_add']) and sel_i: st.session_state.cart.append({"name": sel_i, "qty": q, "price": p})

    if st.session_state.cart:
        df = pd.DataFrame(st.session_state.cart); df['Total'] = df['qty']*df['price']
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.info(f"Total: {df['Total'].sum():,.2f}")
        if st.button(L['btn_del']): st.session_state.cart.pop(); st.rerun()
        
        st.divider()
        use_bk = st.checkbox("Backup", value=True)
        if st.button(L['btn_print'], type="primary"):
            if not st.session_state.c_n: st.error(L['msg_no_name']); st.stop()
            with st.spinner("Processing..."):
                d_data = {'s_n': st.session_state.s_n, 's_t': st.session_state.s_t, 's_a': st.session_state.s_a,
                          'c_n': st.session_state.c_n, 'c_t': st.session_state.c_t, 'c_a': st.session_state.c_a, 'c_tel': st.session_state.c_tel}
                
                # Use UI Lang for PDF Lang
                pdf, grand = generate_pdf_multi_lang(d_data, st.session_state.cart, doc_type, run_no, datetime.now().strftime("%d/%m/%Y"), vat_inc, logo_io, st.session_state.ui_lang)
                
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
                    st.session_state.c_n = r['Name']; st.session_state.c_t = str(r['TaxID'])
                    st.session_state.c_a1 = r['Address1']; st.session_state.c_a2 = r['Address2']; st.session_state.c_tel = str(r['Phone'])
                    st.session_state.q_idx = i + 2
                    if r['Item']:
                        try: p = float(str(r['Price']).replace(',',''))
                        except: p = 0.0
                        st.session_state.cart = [{"name": r['Item'], "qty": 1, "price": p}]
                    st.rerun()
        except: pass
