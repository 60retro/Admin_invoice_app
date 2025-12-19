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

# 🟢🟢 [ส่วนสำคัญ] ใส่ ID ของโฟลเดอร์ Google Drive ที่คุณเตรียมไว้ตรงนี้ 🟢🟢
# ดูจาก URL ของโฟลเดอร์: drive.google.com/drive/folders/XXXXXXXXXXXX
DRIVE_FOLDER_ID = "1_AbCdEfGhIjKlMnOpQrStUvWxYz123456" 

# --- Import สำหรับ Google Drive ---
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# =======================
# ⚙️ Config & Setup
# =======================
st.set_page_config(page_title="Nami Admin Invoice", layout="wide")

try:
    pdfmetrics.registerFont(TTFont('CustomFont', 'THSarabunNewBold.ttf'))
    FONT_NAME = 'CustomFont'
except:
    st.warning("⚠️ ไม่พบฟอนต์ภาษาไทย (THSarabunNewBold.ttf) ระบบจะใช้ฟอนต์มาตรฐาน")
    FONT_NAME = 'Helvetica'

# Connect Google Services (Sheets & Drive)
@st.cache_resource
def get_credentials():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # กรณีรันบน Streamlit Cloud
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scope)
    except:
        # กรณีรันบนเครื่องตัวเอง (Local)
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    return creds

def get_sheet_client():
    creds = get_credentials()
    return gspread.authorize(creds)

def get_drive_service():
    creds = get_credentials()
    # แปลง credentials ให้ใช้กับ google-api-client ได้
    # (oauth2client เก่าหน่อย แต่ใช้ร่วมกับ gspread ได้ดี)
    service = build('drive', 'v3', credentials=creds)
    return service

def get_data(worksheet_name):
    client = get_sheet_client()
    sh = client.open("Invoice_Data") 
    ws = sh.worksheet(worksheet_name)
    return ws.get_all_records(), ws

# =======================
# ☁️ Function Upload to Drive
# =======================
def upload_to_drive(file_obj, filename):
    try:
        service = get_drive_service()
        
        file_metadata = {
            'name': filename,
            'parents': [DRIVE_FOLDER_ID]
        }
        
        # เตรียมไฟล์สำหรับอัปโหลด (Reset pointer)
        file_obj.seek(0)
        media = MediaIoBaseUpload(file_obj, mimetype='application/pdf', resumable=True)
        
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True, file.get('id')
    except Exception as e:
        return False, str(e)

# =======================
# 🖨️ PDF Generation
# =======================
def generate_pdf_buffer(doc_data, items, doc_type="Full"):
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    half_height = height / 2
    
    date_str = datetime.now(pytz.timezone('Asia/Bangkok')).strftime("%d/%m/%Y")
    
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
                lines.append(' '.join(curr)); curr = [w]
        if curr: lines.append(' '.join(curr))
        return lines

    def draw_content(y_base):
        margin = 15 * mm
        top_y = y_base + half_height - margin
        
        c.setFont(FONT_NAME, 14)
        c.drawString(width - margin - 200, top_y + 20, "ร้านนามิ 345 (สำนักงานใหญ่)")
        c.setFont(FONT_NAME, 10)
        c.drawString(width - margin - 200, top_y + 5, "เลขที่ 42 หมู่ 5 ... นนทบุรี 11120")
        
        c.setFont(FONT_NAME, 16)
        title = "ใบกำกับภาษี / ใบเสร็จรับเงิน" if doc_type == "Full" else "ใบกำกับภาษีอย่างย่อ (ABB)"
        c.drawCentredString(width/2, top_y - 20, title)
        
        c.setFont(FONT_NAME, 12)
        c.drawString(margin, top_y - 45, f"ลูกค้า: {doc_data['name']}")
        c.drawString(margin, top_y - 60, f"Tax ID: {doc_data['tax']}")
        
        addr_y = top_y - 75
        c.drawString(margin, addr_y, "ที่อยู่:")
        addr_lines = wrap_text_lines(doc_data['addr'], 300, FONT_NAME, 12)
        for line in addr_lines:
            c.drawString(margin + 35, addr_y, line)
            addr_y -= 12
            
        table_y = addr_y - 20
        c.line(margin, table_y, width-margin, table_y)
        c.drawString(margin, table_y - 15, "รายการ")
        c.drawRightString(width-margin, table_y - 15, "จำนวนเงิน")
        c.line(margin, table_y - 20, width-margin, table_y - 20)
        
        curr_y = table_y - 35
        total = 0
        for item in items:
            name = item['name']
            price = float(item['price'])
            qty = int(item['qty']) if item['qty'] else 1
            amount = price * qty
            total += amount
            
            c.drawString(margin, curr_y, f"{name} (x{qty})")
            c.drawRightString(width-margin, curr_y, f"{amount:,.2f}")
            curr_y -= 15
            
        c.line(margin, curr_y, width-margin, curr_y)
        c.setFont(FONT_NAME, 14)
        c.drawRightString(width-margin, curr_y - 20, f"รวมทั้งสิ้น: {total:,.2f}")

    if doc_type == "ABB":
        draw_content(half_height)
    else:
        draw_content(half_height)
        c.setDash(3, 3); c.line(10, half_height, width-10, half_height); c.setDash(1, 0)
        draw_content(0)

    c.save()
    buffer.seek(0)
    return buffer

# =======================
# 🖥️ User Interface
# =======================
st.title("☁️ Nami Invoice Manager (Web + Drive Backup)")

menu = st.sidebar.selectbox("เมนู", ["รอคิว (Queue)", "จัดการสินค้า", "จัดการลูกค้า"])

if menu == "รอคิว (Queue)":
    st.subheader("📋 รายการรอออกบิล")
    try:
        data, ws = get_data("Queue")
        df = pd.DataFrame(data)
        
        if not df.empty:
            pending_df = df[df['Status'] != 'Done']
            
            for index, row in pending_df.iterrows():
                with st.expander(f"{row['Name']} ({row['Price']} บาท) - {row['Timestamp']}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Tax ID:** {row['TaxID']}")
                        st.write(f"**ที่อยู่:** {row['Address1']} {row['Address2']}")
                    with col2:
                        st.write(f"**สินค้า:** {row['Item']}")
                        st.write(f"**เบอร์:** {row['Phone']}")
                    
                    b1, b2 = st.columns(2)
                    with b1:
                        # ปุ่มนี้จะทำ 2 อย่าง: ให้โหลด + อัปขึ้น Drive
                        if st.button("🖨️ สร้าง PDF & Backup", key=f"pdf_full_{index}", type="primary"):
                            with st.spinner("กำลังสร้างไฟล์และอัปโหลด..."):
                                # 1. Prepare Data
                                doc_data = {
                                    'name': row['Name'], 'tax': row['TaxID'], 
                                    'addr': f"{row['Address1']} {row['Address2']}", 
                                    'doc_no': "WEB-AUTO" 
                                }
                                items = [{'name': row['Item'], 'price': row['Price'], 'qty': 1}]
                                
                                # 2. Generate PDF (In Memory)
                                pdf_buffer = generate_pdf_buffer(doc_data, items, "Full")
                                
                                # 3. Upload to Drive
                                file_name = f"INV_{row['Name']}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
                                success, msg = upload_to_drive(pdf_buffer, file_name)
                                
                                if success:
                                    st.success(f"✅ บันทึกลง Google Drive แล้ว! (ID: {msg})")
                                else:
                                    st.error(f"❌ อัปโหลดไม่สำเร็จ: {msg}")
                                
                                # 4. Show Download Button
                                st.download_button(
                                    label="⬇️ ดาวน์โหลดไฟล์ลงเครื่อง", 
                                    data=pdf_buffer, 
                                    file_name=file_name, 
                                    mime="application/pdf"
                                )
                            
                    with b2:
                        if st.button("✅ จบงาน (Mark Done)", key=f"done_{index}"):
                            cell = ws.find(row['Timestamp'])
                            if cell:
                                ws.update_cell(cell.row, 10, "Done")
                                st.success("Updated!")
                                time.sleep(1)
                                st.rerun()
        else:
            st.info("ไม่มีคิวค้าง")
            
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาด: {e}")

elif menu == "จัดการสินค้า":
    st.subheader("📦 ฐานข้อมูลสินค้า")
    try:
        data, ws = get_data("Items")
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
        
        new_item = st.text_input("เพิ่มสินค้าใหม่")
        if st.button("บันทึกสินค้า"):
            if new_item:
                ws.append_row([new_item])
                st.success("บันทึกแล้ว")
                time.sleep(1)
                st.rerun()
    except:
        st.error("ไม่พบแท็บ 'Items' ใน Google Sheet")

elif menu == "จัดการลูกค้า":
    st.subheader("👥 ฐานข้อมูลลูกค้า")
    try:
        data, ws = get_data("Customers")
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)
    except:
        st.error("ไม่พบแท็บ 'Customers' ใน Google Sheet")