import streamlit as st
import pdfplumber
import re
import pandas as pd

def parse_invoice_data(text: str, tables: list) -> dict:
    """
    Phân tích văn bản và bảng với logic phức tạp hơn để xử lý các trường hợp
    văn bản bị lỗi cấu trúc.
    """
    extracted_data = {}
    
    # --- BỘ REGEX LINH HOẠT ---
    patterns = {
        "ten_cong_ty_ban": r"CÔNG TY CỔ PHẦN Ô TÔ XUYÊN VIỆT",
        "mst_ban": r"Mã số thuế\s*\(Tax code\):\s*(\d+)",
        "dia_chi_ban": r"Địa chỉ\s*\(Address\):\s*(.*?)(?=\n\s*Điện thoại)",
        "dien_thoai": r"Điện thoại\s*\(Tel\):\s*(.*?)\n",
        "so_tai_khoan_ngan_hang": r"Số tài khoản\s*\(Bank account\):\s*(.*?)(?=\s*HÓA ĐƠN GIÁ TRỊ GIA TĂNG)",
        "ky_hieu": r"Ký hiệu\s*\(Serial\):\s*([A-Z0-9]+)",
        "so_hoa_don": r"Số\s*\(No\.\):\s*(\d+)",
        "ngay_thang_nam": r"Ngày\s*\(Date\)\s*(\d{2})\s*tháng\s*\(month\)\s*(\d{2})\s*năm\s*\(year\)\s*(\d{4})",
        "ma_cqt": r"Mã CQT\s*\(Code\):\s*([A-Z0-9]+)",
        "ten_nguoi_mua": r"Họ tên người mua hàng\s*\(Buyer\):\s*(.*?)\n",
        "ten_cong_ty_mua": r"Tên đơn vị\s*\(Company's name\):\s*(.*?)\n",
        "mst_mua": r"Tên đơn vị.*?Mã số thuế\s*\(Tax code\):\s*(\d+)",
        "dia_chi_mua": r"Địa chỉ\s*\(Address\):\s*(Tầng 3,.*?Nam)",
        "hinh_thuc_thanh_toan": r"Hình thức thanh toán\s*\(Payment method\):\s*(.*?)\n",
        "cong_tien_hang": r"Cộng tiền hàng\s*\(Total amount excl\. VAT\):\s*([\d.,]+)",
        "thue_suat_gtgt": r"Thuế suất GTGT\s*\(VAT rate\):\s*(.*?)\s*Tiền thuế GTGT",
        "tien_thue_gtgt": r"Tiền thuế GTGT\s*\(VAT amount\):\s*([\d.,]+)",
        "tong_tien_thanh_toan": r"Tổng tiền thanh toán\s*\(Total amount\):\s*([\d.,]+)",
        "so_tien_bang_chu": r"Số tiền viết bằng chữ\s*\(Total amount in words\):\s*(.*?)\.",
        "ky_boi": r"Ký bởi\s*\(Signed By\):\s*(.*?)\n",
        "ky_ngay": r"Ký ngày\s*\(Signing Date\):\s*(.*?)\n",
        "ma_tra_cuu": r"Mã tra cứu\s*\(Invoice code\):\s*([\w_]+)"
    }

    def clean_text(s):
        return ' '.join(s.strip().replace('\n', ' ').split()) if s else ""

    # 1. Trích xuất thông tin chung từ văn bản
    for key, pattern in patterns.items():
        matches = re.findall(pattern, text, re.DOTALL)
        if matches:
            if key == "ngay_thang_nam":
                extracted_data["Ngày"], extracted_data["Tháng"], extracted_data["Năm"] = matches[0]
            elif key == "so_tai_khoan_ngan_hang":
                parts = matches[0].split('-', 1)
                extracted_data['so_tai_khoan'] = clean_text(parts[0])
                extracted_data['ngan_hang'] = clean_text(parts[1]) if len(parts) > 1 else ""
            elif key == 'mst_mua':
                extracted_data[key] = clean_text(matches[1]) if len(matches) > 1 else clean_text(matches[0])
            else:
                extracted_data[key] = clean_text(matches[0])
        else:
             if key not in ['Ngày', 'Tháng', 'Năm', 'so_tai_khoan', 'ngan_hang']:
                 extracted_data[key] = None
    
    # 2. Trích xuất chi tiết hàng hóa (Ưu tiên từ Bảng)
    items_found_in_table = False
    if tables:
        for table_data in tables:
            if not table_data or len(table_data) < 2: continue
            header = table_data[0]
            if header and len(header) > 2 and header[0] and 'STT' in header[0] and header[1] and 'Tên hàng hóa' in header[1]:
                df = pd.DataFrame(table_data[1:], columns=header)
                items = []
                for _, row in df.iterrows():
                    stt, ten_hang, thanh_tien = row.get(header[0]), row.get(header[1]), row.get(header[2])
                    if stt and ten_hang:
                        items.append({
                            "STT": clean_text(stt),
                            "Tên Hàng hóa, dịch vụ": clean_text(ten_hang),
                            "Thành tiền (VND)": clean_text(thanh_tien)
                        })
                if items:
                    extracted_data['chi_tiet_hang_hoa'] = items
                    items_found_in_table = True
                break
    
    # 3. PHƯƠNG ÁN DỰ PHÒNG: Nếu không tìm thấy trong bảng, "phẫu thuật" văn bản thô
    if not items_found_in_table:
        try:
            total_excl_vat_match = re.search(r"Cộng tiền hàng\s*\(Total amount excl\. VAT\):\s*([\d.,]+)", text)
            if total_excl_vat_match:
                amount_str = total_excl_vat_match.group(1)
                
                block_match = re.search(r"\(Amount\)(.*?)\s*Cộng tiền hàng", text, re.DOTALL)
                if block_match:
                    messy_block = block_match.group(1)
                    
                    stt_match = re.search(r"^\s*(\d+)", messy_block.strip())
                    stt = stt_match.group(1) if stt_match else "1"
                    
                    # Dọn dẹp chuỗi mô tả
                    description = messy_block.replace(amount_str, "")
                    description = re.sub(r'\(đợt\s*\d+\s*(\d+)\)', r'(đợt \1)', description) # Sửa lỗi 'đợt 1 3'
                    
                    extracted_data['chi_tiet_hang_hoa'] = [{
                        "STT": clean_text(stt),
                        "Tên Hàng hóa, dịch vụ": clean_text(description),
                        "Thành tiền (VND)": clean_text(amount_str)
                    }]
        except Exception:
            # Nếu tất cả đều thất bại, gán là None
            extracted_data['chi_tiet_hang_hoa'] = None

    return extracted_data

# --- Giao diện ứng dụng Streamlit (Giữ nguyên như cũ) ---
st.set_page_config(layout="wide", page_title="Trích xuất Hóa đơn PDF")
st.title("📄 Trình trích xuất Thông tin Hóa đơn PDF (Phiên bản Ổn định)")
uploaded_file = st.file_uploader("Tải file PDF của bạn tại đây", type="pdf")

if uploaded_file is not None:
    full_text, tables = "", []
    with st.spinner('Đang đọc cấu trúc file PDF...'):
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    full_text += (page.extract_text(x_tolerance=2) or "") + "\n"
                    tables.extend(page.extract_tables() or [])
        except Exception as e:
            st.error(f"Không thể đọc file PDF. Lỗi: {e}"); st.stop()
    
    with st.expander("Xem dữ liệu thô được trích xuất từ PDF"):
        st.text_area("Văn bản gốc:", full_text, height=300)
        st.json(tables)

    st.markdown("---"); st.header("Kết quả phân tích tự động")
    
    if full_text or tables:
        with st.spinner("Đang phân tích dữ liệu..."):
            data = parse_invoice_data(full_text, tables)
            
            if not data.get('so_hoa_don'):
                 st.error("Không thể trích xuất thông tin cơ bản. Vui lòng kiểm tra văn bản gốc ở trên.")
            else:
                st.success('Trích xuất thành công!')
                with st.container(border=True):
                    st.subheader("1. Thông tin chung Hóa đơn"); col1, col2, col3, col4 = st.columns(4)
                    col1.text(f"Số hóa đơn: {data.get('so_hoa_don', 'N/A')}"); col2.text(f"Ký hiệu: {data.get('ky_hieu', 'N/A')}")
                    ngay_thang_nam = f"{data.get('Ngày', '..')}/{data.get('Tháng', '..')}/{data.get('Năm', '....')}"
                    col3.text(f"Ngày, tháng, năm: {ngay_thang_nam}"); col4.text(f"Mã CQT: {data.get('ma_cqt', 'N/A')}")
                with st.container(border=True):
                    st.subheader("2. Thông tin các bên"); col_ban, col_mua = st.columns(2)
                    with col_ban:
                        st.markdown("**Bên Bán**"); st.text(f"Tên công ty: {data.get('ten_cong_ty_ban', 'N/A')}"); st.text(f"Mã số thuế: {data.get('mst_ban', 'N/A')}"); st.text(f"Địa chỉ: {data.get('dia_chi_ban', 'N/A')}"); st.text(f"Điện thoại: {data.get('dien_thoai', 'N/A')}"); st.text(f"Tài khoản: {data.get('so_tai_khoan', 'N/A')} tại {data.get('ngan_hang', 'N/A')}")
                    with col_mua:
                        st.markdown("**Bên Mua**"); st.text(f"Tên công ty: {data.get('ten_cong_ty_mua', 'N/A')}"); st.text(f"Họ tên người mua: {data.get('ten_nguoi_mua') or '(Không có)'}"); st.text(f"Mã số thuế: {data.get('mst_mua', 'N/A')}"); st.text(f"Địa chỉ: {data.get('dia_chi_mua', 'N/A')}"); st.text(f"Hình thức thanh toán: {data.get('hinh_thuc_thanh_toan', 'N/A')}")
                with st.container(border=True):
                    st.subheader("3. Chi tiết hàng hóa, dịch vụ")
                    if data.get('chi_tiet_hang_hoa'):
                        st.table(pd.DataFrame(data['chi_tiet_hang_hoa']))
                    else:
                        st.error("Không phân tích được bảng chi tiết hàng hóa.")
                with st.container(border=True):
                    st.subheader("4. Tổng cộng thanh toán"); col_sum_1, col_sum_2 = st.columns(2)
                    with col_sum_1:
                        st.text(f"Cộng tiền hàng (chưa VAT): {data.get('cong_tien_hang', 'N/A')}"); st.text(f"Thuế suất GTGT: {data.get('thue_suat_gtgt', 'N/A')}"); st.text(f"Tiền thuế GTGT: {data.get('tien_thue_gtgt', 'N/A')}"); st.success(f"Tổng tiền thanh toán: {data.get('tong_tien_thanh_toan', 'N/A')}")
                    with col_sum_2:
                        st.markdown("**Số tiền viết bằng chữ:**"); st.info(f"{data.get('so_tien_bang_chu', 'N/A')}.")
                with st.container(border=True):
                    st.subheader("5. Thông tin Chữ ký và Tra cứu"); col_sign_1, col_sign_2, col_sign_3 = st.columns(3)
                    col_sign_1.text(f"Ký bởi: {data.get('ky_boi', 'N/A')}"); col_sign_2.text(f"Ngày ký: {data.get('ky_ngay', 'N/A')}"); col_sign_3.text(f"Mã tra cứu: {data.get('ma_tra_cuu', 'N/A')}")