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
st.set_page_config(page_title="Nami Admin V108", layout="wide", page_icon="🧾")

ADMIN_PASSWORD = "3457"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbxlUwV9CaVXHBVmbvRwNCGaNanEsQyOlG8f0kc3BHAS_0X8pLp4KxZCtz_EojYBCvWl6w/exec" # 🟢 ใส่ URL Webhook
SHEET_NAME = "Invoice_Data"
DRIVE_FOLDER_ID = "1zm2KN-W7jCfwYirs-nBVNTlROMyW19ur" # ใส่ ID โฟลเดอร์

# Font Setup
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
    FONT_SIZE_STD = 11
    FONT_SIZE_BOLD = 13
except:
    FONT_NAME = 'Helvetica'
    FONT_SIZE_STD = 10
    FONT_SIZE_BOLD = 12

# ==========================================
# 🔌 2. Connection & Safe Save Logic
# ==========================================
@st.cache_resource
def get_client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    if "gcp_service_account" in st.secrets:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return gspread.authorize(creds)

def robust_save_config(shop_n, shop_t, shop_a):
    """ฟังก์ชันบันทึกที่วนหาบรรทัดเอง ไม่ใช้ .find() เพื่อความชัวร์"""
    try:
        client = get_client()
        ws = client.open(SHEET_NAME).worksheet("Config")
        data = ws.get_all_values()
        
        updates = []
        for i, row in enumerate(data):
            key = str(row[0]).strip()
            if key == "ShopName": updates.append({"range": f"B{i+1}", "values": [[shop_n]]})
            elif key == "TaxID": updates.append({"range": f"B{i+1}", "values": [[shop_t]]})
            elif key == "Address": updates.append({"range": f"B{i+1}", "values": [[shop_a]]})
            
        if updates:
            ws.batch_update(updates)
            return True, "บันทึกสำเร็จ"
        return False, "ไม่พบ Key ใน Config"
    except Exception as e:
        return False, str(e)

def upload_via_webhook(pdf_bytes, filename):
    try:
        payload = {
            "filename": filename,
            "mimeType": "application/pdf",
            "file": base64.b64encode(pdf_bytes).decode('utf-8'),
            "folderId": DRIVE_FOLDER_ID
        }
        requests.post(APPS_SCRIPT_URL, json=payload)
        return True
    except: return False

# ==========================================
# 🖨️ 3. PDF Generator (Replica from Image)
# ==========================================
def generate_pdf_replica(doc_data, items, doc_type, running_no, date_str, vat_inc, logo_upload):
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

    def draw_half(y_base, is_copy):
        margin = 10 * mm
        top_y = y_base + half_height - margin
        page_w = width - (2 * margin)
        
        # 1. Logo (Left)
        if logo_upload:
            try:
                logo_upload.seek(0)
                img = ImageReader(logo_upload)
                c.drawImage(img, margin, top_y - 20*mm, width=35*mm, height=18*mm, preserveAspectRatio=True, mask='auto')
            except: pass

        # 2. Shop Box (Right, Rounded)
        box_w = 90 * mm
        box_h = 25 * mm
        box_x = width - margin - box_w
        box_y = top_y - 20*mm
        
        c.setLineWidth(0.5)
        c.roundRect(box_x, box_y, box_w, box_h, 6, stroke=1, fill=0)
        
        # Shop Details inside box
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        c.drawString(box_x + 3*mm, box_y + box_h - 5*mm, f"{doc_data['shop_name']} (สำนักงานใหญ่)")
        
        addr_lines = wrap_text(doc_data['shop_addr'], box_w - 6*mm, FONT_NAME, FONT_SIZE_STD - 2)
        cur_ay = box_y + box_h - 10*mm
        c.setFont(FONT_NAME, FONT_SIZE_STD - 2)
        for l in addr_lines:
            c.drawString(box_x + 3*mm, cur_ay, l)
            cur_ay -= 4*mm
        # c.drawString(box_x + 3*mm, cur_ay, f"โทร: ...")

        # 3. Title
        header_txt = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        if is_copy: header_txt = "สำเนา " + header_txt
        else: header_txt = "ต้นฉบับ " + header_txt
        
        c.setFont(FONT_NAME, FONT_SIZE_BOLD + 2)
        c.drawCentredString(width/2, top_y - 30*mm, header_txt)

        # 4. Info Bar
        info_y = top_y - 38*mm
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        c.drawString(margin, info_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['shop_tax']}")
        c.drawRightString(width - margin, info_y, f"เลขที่ : {running_no}")

        # 5. Customer & Doc Details Box
        rect_y = info_y - 2*mm
        rect_h = 30 * mm
        rect_btm = rect_y - rect_h
        
        c.rect(margin, rect_btm, page_w, rect_h) # Main Box
        split_x = width - margin - 75*mm
        c.line(split_x, rect_y, split_x, rect_btm) # Vertical Split
        
        # Customer Info (Left)
        cx = margin + 3*mm; cy = rect_y - 5*mm
        c.drawRightString(cx + 40*mm, cy, "เลขประจำตัวผู้เสียภาษีอากร :")
        c.drawString(cx + 42*mm, cy, doc_data['cust_tax'])
        cy -= 5*mm
        c.drawRightString(cx + 40*mm, cy, "ชื่อลูกค้า :")
        c.drawString(cx + 42*mm, cy, doc_data['cust_name'])
        cy -= 5*mm
        c.drawRightString(cx + 40*mm, cy, "ที่อยู่ :")
        # Wrap address
        c_addr_lines = wrap_text(doc_data['cust_addr'], split_x - (cx + 42*mm), FONT_NAME, FONT_SIZE_STD)
        cay = cy
        for l in c_addr_lines[:2]:
            c.drawString(cx + 42*mm, cay, l)
            cay -= 5*mm
        c.drawRightString(cx + 40*mm, rect_btm + 2*mm, "โทรศัพท์ :")
        c.drawString(cx + 42*mm, rect_btm + 2*mm, doc_data['cust_tel'])

        # Doc Details (Right)
        dx = split_x + 3*mm; dy = rect_y - 5*mm
        c.drawRightString(dx + 30*mm, dy, "วันที่เอกสาร :")
        c.drawString(dx + 32*mm, dy, date_str)
        dy -= 5*mm
        c.drawRightString(dx + 30*mm, dy, "พนักงานขาย :")
        c.drawString(dx + 32*mm, dy, "-")
        dy -= 5*mm
        c.drawRightString(dx + 30*mm, dy, "เงื่อนไขการชำระ :")
        c.drawString(dx + 32*mm, dy, "สด")

        # 6. Table
        tbl_top = rect_btm - 2*mm
        header_h = 7*mm
        
        # Header BG
        c.setFillColorRGB(0.8, 0.8, 0.8)
        c.rect(margin, tbl_top - header_h, page_w, header_h, fill=1, stroke=1)
        c.setFillColorRGB(0, 0, 0)
        
        cols = [12*mm, 85*mm, 20*mm, 30*mm, 30*mm] # Widths
        col_x = [margin]
        for cw in cols: col_x.append(col_x[-1] + cw) # Calc positions
        
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]
        c.setFont(FONT_NAME, FONT_SIZE_BOLD)
        for i, h in enumerate(headers):
            c.drawCentredString(col_x[i] + cols[i]/2, tbl_top - 5*mm, h)
            
        # Items Loop
        cur_y = tbl_top - header_h
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        total = 0
        
        for idx, item in enumerate(items, 1):
            if idx > 12: break
            nm = item['name']; qty = item['qty']; price = item['price']
            amt = qty * price; total += amt
            
            row_h = 7*mm
            text_y = cur_y - 5*mm
            
            c.drawCentredString(col_x[0] + cols[0]/2, text_y, str(idx))
            c.drawString(col_x[1] + 2*mm, text_y, str(nm))
            c.drawRightString(col_x[2] + cols[2] - 2*mm, text_y, f"{qty:,.0f}")
            c.drawRightString(col_x[3] + cols[3] - 2*mm, text_y, f"{price:,.2f}")
            c.drawRightString(col_x[4] + cols[4] - 2*mm, text_y, f"{amt:,.2f}")
            
            cur_y -= row_h
            
        # Draw Main Table Box & Vertical Lines
        table_btm = top_y - 125*mm # Fix height like image
        c.rect(margin, table_btm, page_w, (tbl_top - table_btm)) # Outer box
        
        for x in col_x[1:-1]: # Vertical lines
            c.line(x, tbl_top, x, table_btm)
            
        # 7. Footer
        ft_top = table_btm
        ft_h = 7*mm
        
        if vat_inc:
            grand = total; pre = total * 100 / 107; vat = total - pre
        else:
            pre = total; vat = total * 0.07; grand = total + vat
            
        labels = ["จำนวนเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        values = [f"{total:,.2f}", "-", f"{pre:,.2f}", f"{vat:,.2f}", f"{grand:,.2f}"]
        
        cur_fy = ft_top
        c.setFont(FONT_NAME, FONT_SIZE_STD)
        
        # Footer Grid
        for i in range(5):
            c.rect(col_x[3], cur_fy - ft_h, cols[3], ft_h)
            c.rect(col_x[4], cur_fy - ft_h, cols[4], ft_h)
            
            c.drawRightString(col_x[4] - 2*mm, cur_fy - 5*mm, labels[i])
            c.drawRightString(col_x[5] - 2*mm, cur_fy - 5*mm, values[i])
            cur_fy -= ft_h
            
        # Signature
        sig_y = cur_fy - 10*mm
        c.drawString(margin + 10*mm, sig_y, "ผู้รับสินค้า ............................................")
        c.drawString(width - margin - 60*mm, sig_y, "ผู้รับเงิน ............................................")

    # Draw Original (Top)
    draw_half(half_height, False)
    # Draw Dotted Line
    c.setDash(2, 2); c.line(5*mm, half_height, width-5*mm, half_height); c.setDash(1, 0)
    # Draw Copy (Bottom)
    draw_half(0, True)
    
    c.save(); buffer.seek(0); return buffer

# ==========================================
# 🖥️ 4. Main App Logic
# ==========================================
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['f_n','f_t','f_a','f_tel','s_n','s_t','s_a']:
    if k not in st.session_state: st.session_state[k] = ""

# --- Sidebar ---
with st.sidebar:
    st.title("Admin Menu")
    
    if st.session_state.logged_in:
        if st.button("🔄 Sync DB"): st.rerun()
        
        st.divider()
        st.write("☁️ **Queue (Live)**")
        try:
            client = get_client(); sh = client.open(SHEET_NAME)
            # Load Live Data
            q_recs = sh.worksheet("Queue").get_all_records()
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
                    
                    # Mark Done
                    sh.worksheet("Queue").update_cell(i+2, 10, "Done")
                    st.rerun()
        except: st.caption("No Queue / Connect Error")
        
        st.divider()
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False; st.rerun()
            
    else:
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if pwd == ADMIN_PASSWORD: st.session_state.logged_in = True; st.rerun()
            else: st.error("Wrong Password")
        st.stop()

# --- Main Content ---
st.title("🧾 Nami Invoice (V108 Replica)")

# Load Config & DB
try:
    ws_conf = sh.worksheet("Config")
    conf_list = ws_conf.get_all_values()
    conf = {str(r[0]).strip(): str(r[1]).strip() for r in conf_list if len(r)>=2}
    
    # Init Shop Info
    if not st.session_state.s_n:
        st.session_state.s_n = conf.get("ShopName","")
        st.session_state.s_t = conf.get("TaxID","")
        st.session_state.s_a = conf.get("Address","")
        
    # Load Items/Custs
    try: item_df = pd.DataFrame(sh.worksheet("Items").get_all_records())
    except: item_df = pd.DataFrame(columns=['ItemName'])
    try: cust_df = pd.DataFrame(sh.worksheet("Customers").get_all_records())
    except: cust_df = pd.DataFrame(columns=['Name'])
except: st.error("DB Error"); st.stop()

col_L, col_R = st.columns([1.2, 1])

with col_L:
    # 1. Shop & Logo
    with st.expander("🏠 ข้อมูลร้านค้า & โลโก้", expanded=True):
        c1, c2 = st.columns(2)
        st.session_state.s_n = c1.text_input("ชื่อร้าน", st.session_state.s_n)
        st.session_state.s_t = c2.text_input("Tax ID", st.session_state.s_t)
        st.session_state.s_a = st.text_area("ที่อยู่", st.session_state.s_a, height=80)
        logo_up = st.file_uploader("โลโก้ (PNG/JPG)", type=['png','jpg','jpeg'])
        
        if st.button("💾 บันทึกข้อมูลร้าน"):
            ok, msg = robust_save_config(st.session_state.s_n, st.session_state.s_t, st.session_state.s_a)
            if ok: st.success(msg)
            else: st.error(msg)

    # 2. Customer
    st.subheader("👤 ข้อมูลลูกค้า")
    cust_opts = [""] + list(cust_df['Name'].unique()) if not cust_df.empty else [""]
    sel_cust = st.selectbox("🔍 ค้นหาลูกค้า", cust_opts)
    
    if sel_cust and sel_cust != st.session_state.get('last_c'):
        r = cust_df[cust_df['Name'] == sel_cust].iloc[0]
        st.session_state.f_n = r['Name']
        st.session_state.f_t = str(r['TaxID'])
        st.session_state.f_a = f"{r['Address1']} {r['Address2']}"
        st.session_state.f_tel = str(r['Phone'])
        st.session_state.last_c = sel_cust; st.rerun()

    c1, c2 = st.columns(2)
    st.session_state.f_n = c1.text_input("ชื่อลูกค้า", st.session_state.f_n)
    st.session_state.f_t = c2.text_input("Tax ID (ลูกค้า)", st.session_state.f_t)
    st.session_state.f_a = st.text_area("ที่อยู่ลูกค้า", st.session_state.f_a)
    st.session_state.f_tel = st.text_input("เบอร์โทร", st.session_state.f_tel)
    
    if st.button("🧹 ล้างค่า"):
        for k in ['f_n','f_t','f_a','f_tel']: st.session_state[k] = ""; 
        st.rerun()

    # 3. Doc Settings
    st.divider()
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    run_no = st.text_input("เลขที่เอกสาร", value=conf.get(run_key, "INV-000"))
    doc_date = st.date_input("วันที่", datetime.now())
    vat_inc = st.checkbox("รวม VAT แล้ว", value=True)

with col_R:
    # 4. Cart
    st.subheader("🛒 รายการสินค้า")
    item_opts = [""] + list(item_df['ItemName'].unique()) if not item_df.empty else [""]
    sel_item = st.selectbox("สินค้า", item_opts)
    
    c1, c2, c3 = st.columns([1,1,1])
    qty = c1.number_input("จำนวน", 1, value=1)
    price = c2.number_input("ราคา", 0.0)
    if c3.button("➕ เพิ่ม"):
        if sel_item: st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    if st.session_state.cart:
        df_cart = pd.DataFrame(st.session_state.cart)
        df_cart['Total'] = df_cart['qty'] * df_cart['price']
        st.dataframe(df_cart, use_container_width=True, hide_index=True)
        st.info(f"💰 รวม: {df_cart['Total'].sum():,.2f}")
        
        if st.button("❌ ลบรายการล่าสุด"): st.session_state.cart.pop(); st.rerun()
        
        st.divider()
        use_backup = st.checkbox("Backup ลง Drive", value=True)
        
        if st.button("🖨️ ออกใบกำกับภาษี", type="primary", use_container_width=True):
            if not st.session_state.f_n: st.error("ระบุชื่อลูกค้า"); st.stop()
            
            with st.spinner("Processing..."):
                # Save SalesLog
                try: sh.worksheet("SalesLog").append_row([str(doc_date), df_cart['Total'].sum()])
                except: pass
                
                # Update Running No
                try:
                    p = re.match(r"([A-Za-z0-9\-]+?)(\d+)$", run_no)
                    if p:
                        nxt = f"{p.group(1)}{str(int(p.group(2))+1).zfill(len(p.group(2)))}"
                        # Update Config robustly
                        robust_save_config(st.session_state.s_n, st.session_state.s_t, st.session_state.s_a) # Save shop info just in case
                        # Update No
                        cell = ws_conf.find(run_key)
                        ws_conf.update_cell(cell.row, 2, nxt)
                except: pass
                
                # Gen PDF
                d_data = {
                    "shop_name": st.session_state.s_n, "shop_tax": st.session_state.s_t, "shop_addr": st.session_state.s_a,
                    "cust_name": st.session_state.f_n, "cust_tax": st.session_state.f_t, "cust_addr": st.session_state.f_a, "cust_tel": st.session_state.f_tel
                }
                pdf = generate_pdf_replica(d_data, st.session_state.cart, doc_type, run_no, str(doc_date), vat_inc, logo_up)
                fname = f"INV_{run_no}.pdf"
                
                # Backup
                bk_msg = ""
                if use_backup:
                    if upload_via_webhook(pdf, fname): bk_msg = "✅ Backup OK"
                    else: bk_msg = "⚠️ Backup Failed"
                
                st.success(f"เรียบร้อย! {bk_msg}")
                st.download_button("⬇️ PDF", pdf, fname, "application/pdf")
                st.session_state.cart = [] # Clear
