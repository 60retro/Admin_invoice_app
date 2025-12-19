import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime
import pytz
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
import textwrap
import re
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# ⚙️ 1. ตั้งค่าระบบ & รหัสผ่าน
# ==========================================
st.set_page_config(page_title="Nami Admin V90", layout="wide", page_icon="🧾")

# 🔒 รหัสผ่านเข้าใช้งาน (Admin Password)
ADMIN_PASSWORD = "1234" 

# 🟢 ใส่ ID โฟลเดอร์ Google Drive สำหรับ Backup ไฟล์ PDF
DRIVE_FOLDER_ID = "1hFTlfxFhAeew_LUjC224pG2Zs2wsE6lG" 

# ชื่อไฟล์ Google Sheet
SHEET_NAME = "Invoice_Data"

# โหลดฟอนต์ไทย
try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except:
    FONT_NAME = 'Helvetica' # Fallback

# ==========================================
# 🔌 2. เชื่อมต่อ Google Services
# ==========================================
@st.cache_resource
def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # รองรับทั้ง Local และ Cloud
    if "gcp_service_account" in st.secrets:
        return ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    else:
        return ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

def get_sheet_client():
    return gspread.authorize(get_credentials())

def get_drive_service():
    return build('drive', 'v3', credentials=get_credentials())

# ==========================================
# 🛠️ 3. Helper Functions (เหมือน V90 Desktop)
# ==========================================
def smart_clean_address(addr1, addr2):
    """แยก แขวง/ตำบล/เขต/อำเภอ แบบ V77+"""
    house = str(addr1); dist = ""; prov = str(addr2)
    match_amp = re.search(r'(เขต|อำเภอ|อ\.)\s*([^\s]+)', prov)
    if match_amp:
        extracted = match_amp.group(0)
        dist += extracted + " "
        prov = prov.replace(extracted, "").strip()
    match_tum = re.search(r'(แขวง|ตำบล|ต\.)\s*([^\s]+)', house)
    if match_tum:
        extracted = match_tum.group(0)
        dist = extracted + " " + dist
        house = house.replace(extracted, "").strip()
    return house.strip(), dist.strip(), prov.strip()

def upload_to_drive(file_obj, filename):
    try:
        service = get_drive_service()
        file_metadata = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype='application/pdf', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True, file.get('id')
    except Exception as e:
        return False, str(e)

# ==========================================
# 🖨️ 4. PDF Engine (Logic V87-V90 Desktop เป๊ะๆ)
# ==========================================
def generate_pdf_v90(doc_data, items, doc_type, running_no):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    half_height = height / 2
    
    date_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%d/%m/%Y")

    # Manual Wrap Logic (เหมือน Desktop)
    def wrap_text_lines(text, width_limit, font, size):
        c.setFont(font, size)
        lines = []
        words = str(text).split(' ')
        curr = []
        for w in words:
            test = ' '.join(curr + [w])
            if pdfmetrics.stringWidth(test, font, size) <= width_limit:
                curr.append(w)
            else:
                if curr: lines.append(' '.join(curr)); curr = [w]
                else: lines.append(w); curr = []
        if curr: lines.append(' '.join(curr))
        return lines

    def draw_invoice(y_offset):
        margin = 15 * mm
        base_y = y_offset
        top_y = base_y + half_height - margin
        page_w = width - (2 * margin)
        font_size_std = 11
        font_size_bold = 12
        line_height = 12
        
        # --- Header ---
        # (Logo would go here if file exists)
        
        # Shop Box (V87 Fix)
        box_w = 260; box_h = 80 
        box_x = width - margin - box_w; box_y = top_y - box_h + 10
        c.setLineWidth(1); c.roundRect(box_x, box_y, box_w, box_h, 8, stroke=1, fill=0)
        c.setFont(FONT_NAME, font_size_bold)
        c.drawString(box_x + 10, box_y + box_h - 15, doc_data['shop_name']) # Shop Name
        c.setFont(FONT_NAME, font_size_std)
        
        raw_addr = doc_data['shop_addr'].split('\n')
        cur_sy = box_y + box_h - 30
        for line in raw_addr:
            wrapped = wrap_text_lines(line, box_w - 20, FONT_NAME, font_size_std)
            for w_line in wrapped:
                if cur_sy < box_y + 5: break
                c.drawString(box_x + 10, cur_sy, w_line); cur_sy -= line_height

        # Title & Doc Info
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        title_y = box_y - 20; center_x_left = margin + ((box_x - margin) / 2)
        c.setFont(FONT_NAME, font_size_bold + 2); c.drawCentredString(center_x_left, title_y, f"ต้นฉบับ {title}")
        
        bar_y = title_y - 20 
        c.setFont(FONT_NAME, font_size_std)
        c.drawString(margin, bar_y, f"เลขประจำตัวผู้เสียภาษีอากร : {doc_data['shop_tax']}")
        c.drawRightString(width - margin, bar_y, f"เลขที่ : {running_no}")

        # --- Customer Box ---
        info_box_y = bar_y - 5; info_box_h = 75; info_box_btm = info_box_y - info_box_h
        c.rect(margin, info_box_btm, page_w, info_box_h)
        div_x = width - margin - 200
        c.line(div_x, info_box_y, div_x, info_box_btm)
        
        # Left Side
        cx = margin + 10; cy = info_box_y - 12; label_gap = 12; label_anchor = cx + 110 
        c.setFont(FONT_NAME, font_size_bold); c.drawRightString(label_anchor, cy, "เลขประจำตัวผู้เสียภาษีอากร :")
        c.setFont(FONT_NAME, font_size_std); c.drawString(label_anchor + 5, cy, doc_data['cust_tax'])
        
        current_y = cy - label_gap 
        c.setFont(FONT_NAME, font_size_bold); c.drawRightString(label_anchor, current_y, "ชื่อลูกค้า :")
        c.setFont(FONT_NAME, font_size_std)
        
        avail_w = div_x - (label_anchor + 5) - 5 # V87 Calculation
        name_lines = wrap_text_lines(doc_data['cust_name'], avail_w, FONT_NAME, font_size_std)
        for line in name_lines:
            c.drawString(label_anchor + 5, current_y, line); current_y -= 10
        current_y -= 2

        c.setFont(FONT_NAME, font_size_bold); c.drawRightString(label_anchor, current_y, "ที่อยู่ :")
        c.setFont(FONT_NAME, font_size_std)
        addr_lines = wrap_text_lines(doc_data['cust_addr'], avail_w, FONT_NAME, font_size_std)
        for line in addr_lines:
            c.drawString(label_anchor + 5, current_y, line); current_y -= 10
            
        tel_y = info_box_btm + 5 # V86 Bottom Lock
        c.setFont(FONT_NAME, font_size_bold); c.drawRightString(label_anchor, tel_y, "โทรศัพท์ :")
        c.setFont(FONT_NAME, font_size_std); c.drawString(label_anchor + 5, tel_y, doc_data['cust_tel'])

        # Right Side
        dx = div_x + 10; dy = info_box_y - 12
        c.setFont(FONT_NAME, font_size_bold)
        c.drawRightString(dx + 80, dy, "วันที่เอกสาร :"); c.drawRightString(dx + 80, dy - label_gap, "พนักงานขาย :"); c.drawRightString(dx + 80, dy - label_gap*2, "เงื่อนไขการชำระ :")
        c.setFont(FONT_NAME, font_size_std)
        c.drawString(dx + 85, dy, date_str); c.drawString(dx + 85, dy - label_gap*2, "สด")

        # --- Table ---
        tbl_top = info_box_btm - 5
        c.setFillColorRGB(0.2, 0.2, 0.2); c.rect(margin, tbl_top - 14, page_w, 14, fill=1, stroke=1)
        c.setFillColorRGB(1, 1, 1)
        col_w = [25, page_w - 215, 45, 70, 75] 
        col_x = [margin, margin+col_w[0], margin+col_w[0]+col_w[1], margin+col_w[0]+col_w[1]+col_w[2], margin+col_w[0]+col_w[1]+col_w[2]+col_w[3]]
        
        c.setFont(FONT_NAME, font_size_bold)
        headers = ["ลำดับ", "รายการสินค้า", "จำนวน", "ราคาต่อหน่วย", "จำนวนเงิน"]
        for i, h in enumerate(headers):
            c.drawCentredString(col_x[i] + col_w[i]/2, tbl_top - 10, h)
        c.setFillColorRGB(0, 0, 0)
        
        current_y = tbl_top - 14
        c.setFont(FONT_NAME, font_size_std)
        
        # Items Loop (V87 Manual 3-Line Logic)
        total = 0
        for idx, item in enumerate(items, start=1):
            if idx > 15: break
            name = item['name']; qty = item['qty']; price = item['price']
            amount = qty * price; total += amount
            
            name_lines = wrap_text_lines(str(name), col_w[1] - 10, FONT_NAME, font_size_std)
            if len(name_lines) > 3: name_lines = name_lines[:3]
            row_h = 45 
            
            text_top_y = current_y - 12
            c.drawCentredString(col_x[0] + col_w[0]/2, text_top_y, str(idx))
            for i, line in enumerate(name_lines): c.drawString(col_x[1] + 5, text_top_y - (i * 12), line)
            c.drawRightString(col_x[2] + col_w[2] - 10, text_top_y, f"{qty:,.0f}")
            c.drawRightString(col_x[3] + col_w[3] - 5, text_top_y, f"{price:,.2f}")
            c.drawRightString(col_x[4] + col_w[4] - 5, text_top_y, f"{amount:,.2f}")
            current_y -= row_h
            c.setLineWidth(0.5); c.line(margin, current_y, width - margin, current_y)

        # Footer
        table_btm = current_y
        c.rect(margin, table_btm, page_w, (tbl_top - 14) - table_btm)
        for x in col_x[1:]: c.line(x, tbl_top - 14, x, table_btm)
        
        # Calculate VAT
        vat_rate = 0.07
        if True: # Assuming VAT Included logic for Web
            grand = total; before_vat = total / 1.07; vat = grand - before_vat
        
        footer_labels = ["จำนวนเงิน", "ส่วนลด", "ราคาสินค้า/บริการ", "ภาษีมูลค่าเพิ่ม 7%", "จำนวนเงินรวมทั้งสิ้น"]
        footer_values = [f"{before_vat+vat:,.2f}", "-", f"{before_vat:,.2f}", f"{vat:,.2f}", f"{grand:,.2f}"]
        
        footer_row_h = 14; footer_top = table_btm
        c.line(col_x[4], footer_top, col_x[4], footer_top - (5 * footer_row_h))
        c.line(width - margin, footer_top, width - margin, footer_top - (5 * footer_row_h))
        
        for i in range(5):
            r_top = footer_top - (i * footer_row_h); r_btm = r_top - footer_row_h; t_y = r_btm + 4
            c.line(col_x[4], r_btm, width - margin, r_btm)
            c.setFont(FONT_NAME, font_size_std); c.drawRightString(col_x[4] - 15, t_y, footer_labels[i] + " :")
            if i == 4: c.setFont(FONT_NAME, font_size_bold)
            else: c.setFont(FONT_NAME, font_size_std)
            c.drawRightString(width - margin - 5, t_y, footer_values[i])
            
        # Signature
        sig_y = footer_top - (5 * footer_row_h) - 25
        c.setFont(FONT_NAME, font_size_std)
        c.drawString(margin + 20, sig_y, "ผู้รับสินค้า ...........................................................")
        c.drawString(width - margin - 220, sig_y, "ผู้รับเงิน ...........................................................")

    if doc_type == "ABB":
        draw_invoice(half_height)
    else:
        draw_invoice(half_height)
        c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0)
        draw_invoice(0)

    c.save()
    buffer.seek(0)
    return buffer

# ==========================================
# 🖥️ 5. Main App UI
# ==========================================

# --- Login System ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown("## 🔒 Admin Login")
        pwd = st.text_input("กรุณาใส่รหัสผ่าน", type="password")
        if st.button("เข้าสู่ระบบ"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("รหัสผ่านไม่ถูกต้อง")
    st.stop() # หยุดการทำงานถ้ารหัสไม่ผ่าน

# --- Main App (Logged In) ---
st.title("🧾 Nami Invoice (V90 Web Edition)")

# Load Data from Sheet
try:
    client = get_sheet_client()
    sh = client.open(SHEET_NAME)
    
    # Load Config (Seller Info)
    ws_conf = sh.worksheet("Config")
    conf_data = dict(ws_conf.get_all_values()) # คาดหวัง A=Key, B=Value
    seller_info = {
        "n": conf_data.get("ShopName", "ชื่อร้าน..."),
        "t": conf_data.get("TaxID", "000..."),
        "a": conf_data.get("Address", "ที่อยู่...")
    }
    
    # Load Customers & Items
    cust_df = pd.DataFrame(sh.worksheet("Customers").get_all_records())
    item_df = pd.DataFrame(sh.worksheet("Items").get_all_records())
    
except Exception as e:
    st.error(f"เชื่อมต่อ Database ไม่สำเร็จ: {e}")
    st.stop()

# --- Layout Division ---
col_L, col_R = st.columns([1, 1.5])

with col_L:
    # --- 1. Seller Info ---
    with st.expander("🔒 ข้อมูลผู้ขาย (Admin)", expanded=False):
        st.text_input("ชื่อร้าน", value=seller_info['n'], disabled=True)
        st.text_input("Tax ID", value=seller_info['t'], disabled=True)
        st.text_area("ที่อยู่", value=seller_info['a'], disabled=True, height=80)

    # --- 2. Customer Info ---
    st.markdown("### 👤 ข้อมูลลูกค้า")
    
    # Search
    search_term = st.selectbox("🔍 ค้นหาลูกค้า (ชื่อ)", [""] + list(cust_df['Name'].unique()))
    
    found_cust = {}
    if search_term:
        row = cust_df[cust_df['Name'] == search_term].iloc[0]
        # Clean Address Logic
        h, d, p = smart_clean_address(row['Address1'], row['Address2'])
        found_cust = {
            "n": row['Name'], "t": str(row['TaxID']), "h": h, "d": d, "p": p, "tel": str(row['Phone'])
        }
        
    c_name = st.text_input("ชื่อลูกค้า", value=found_cust.get("n", ""))
    c_tax = st.text_input("เลขผู้เสียภาษี", value=found_cust.get("t", ""))
    c_h = st.text_input("ที่อยู่ (เลขที่/ถนน)", value=found_cust.get("h", ""))
    
    cc1, cc2 = st.columns(2)
    c_d = cc1.text_input("ตำบล/อำเภอ", value=found_cust.get("d", ""))
    c_p = cc2.text_input("จังหวัด/รหัส", value=found_cust.get("p", ""))
    
    c_tel = st.text_input("เบอร์โทร", value=found_cust.get("tel", ""))

    # --- 3. Document Settings ---
    st.markdown("---")
    st.markdown("### 📄 ตั้งค่าเอกสาร")
    doc_type = st.radio("ประเภท", ["Full", "ABB"], horizontal=True)
    
    # Running No Logic
    run_key = "Full_No" if doc_type == "Full" else "Abb_No"
    current_run = conf_data.get(run_key, "INV-000")
    
    st.info(f"เลขที่เอกสารปัจจุบัน: **{current_run}**")

with col_R:
    # --- 4. Items Management ---
    st.markdown("### 🛒 รายการสินค้า")
    
    # Session State for Cart
    if 'cart' not in st.session_state: st.session_state.cart = []
    
    # Add Item
    ic1, ic2, ic3, ic4 = st.columns([3, 1, 1, 1])
    with ic1: 
        sel_item = st.selectbox("เลือกสินค้า", [""] + list(item_df['ItemName'].unique()))
    with ic2: 
        qty = st.number_input("จำนวน", min_value=1, value=1)
    with ic3: 
        price = st.number_input("ราคา", min_value=0.0, value=0.0)
    with ic4:
        st.write("")
        st.write("")
        if st.button("➕ เพิ่ม"):
            if sel_item:
                st.session_state.cart.append({"name": sel_item, "qty": qty, "price": price})
    
    # Show Cart
    if st.session_state.cart:
        cart_df = pd.DataFrame(st.session_state.cart)
        cart_df['Total'] = cart_df['qty'] * cart_df['price']
        st.dataframe(cart_df, use_container_width=True)
        
        # Remove Item
        if st.button("ลบรายการล่าสุด", type="secondary"):
            st.session_state.cart.pop()
            st.rerun()
            
        grand_total = cart_df['Total'].sum()
        st.markdown(f"### 💰 ยอดรวม: `{grand_total:,.2f}` บาท")
        
        st.markdown("---")
        
        # --- 5. Actions ---
        if st.button("🖨️ ออกใบกำกับภาษี & Backup Cloud", type="primary", use_container_width=True):
            if not c_name:
                st.error("กรุณาระบุชื่อลูกค้า")
            else:
                with st.spinner("กำลังสร้างไฟล์..."):
                    # Prepare Data
                    doc_data = {
                        "shop_name": seller_info['n'], "shop_tax": seller_info['t'], "shop_addr": seller_info['a'],
                        "cust_name": c_name, "cust_tax": c_tax, "cust_tel": c_tel,
                        "cust_addr": f"{c_h} {c_d} {c_p}".strip()
                    }
                    
                    # Generate PDF
                    pdf_buffer = generate_pdf_v90(doc_data, st.session_state.cart, doc_type, current_run)
                    
                    # Upload to Drive
                    fname = f"INV_{c_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                    ok, res = upload_to_drive(pdf_buffer, fname)
                    
                    if ok:
                        st.success(f"✅ บันทึกขึ้น Cloud แล้ว (ID: {res})")
                        
                        # Update Running No
                        # (Simple logic: Increment last digits)
                        try:
                            prefix = re.match(r"([A-Za-z\-]+)", current_run).group(1)
                            num = int(re.search(r"(\d+)$", current_run).group(1)) + 1
                            new_run = f"{prefix}{str(num).zfill(len(current_run)-len(prefix))}"
                            
                            # Save to Sheet
                            cell = ws_conf.find(run_key)
                            ws_conf.update_cell(cell.row, 2, new_run)
                        except: pass
                        
                        # Download Button
                        st.download_button("⬇️ ดาวน์โหลด PDF", data=pdf_buffer, file_name=fname, mime="application/pdf")
                        
                        # Clear Cart Logic (Optional)
                        # st.session_state.cart = []
                    else:
                        st.error(f"Backup ล้มเหลว: {res}")

    else:
        st.info("ยังไม่มีสินค้าในตะกร้า")

# --- Sidebar: Queue Manager ---
with st.sidebar:
    st.header("☁️ รายการรอคิว (Queue)")
    if st.button("🔄 รีเฟรชคิว"):
        st.rerun()
        
    try:
        q_data = sh.worksheet("Queue").get_all_records()
        q_df = pd.DataFrame(q_data)
        pending = q_df[q_df['Status'] != 'Done']
        
        if not pending.empty:
            for i, r in pending.iterrows():
                st.warning(f"**{r['Name']}** ({r['Price']})")
                if st.button("ดึงข้อมูล", key=f"pull_{i}"):
                    # Logic to pull data to form
                    # (In Streamlit, tricky to push to widgets directly without session state acrobatics)
                    # For simplicity: Just show details to copy
                    st.write(f"Tax: {r['TaxID']}")
                    st.write(f"Addr: {r['Address1']} {r['Address2']}")
        else:
            st.success("ไม่มีคิวค้าง")
    except: pass
