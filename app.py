import streamlit as st
import pdfplumber
import re
import pandas as pd
from typing import Dict, Any

def parse_invoice_data(text: str) -> Dict[str, Any]:
    """
    Hàm phân tích hóa đơn với logic xử lý từng dòng để đảm bảo độ chính xác
    và giải quyết triệt để vấn đề thông tin bị dính liền.
    """
    data = {}
    lines = text.split('\n')

    def clean_text(s: str) -> str:
        return ' '.join(s.strip().split()) if s and isinstance(s, str) else ""

    # --- Xử lý từng dòng văn bản ---
    for i, line in enumerate(lines):
        line = clean_text(line)

        # Sử dụng if/elif để tránh một dòng bị xử lý nhiều lần
        if "CÔNG TY CỔ PHẦN Ô TÔ XUYÊN VIỆT" in line and "ten_cong_ty_ban" not in data:
            data["ten_cong_ty_ban"] = line
        
        elif "Mã số thuế (Tax code):" in line:
            value = clean_text(line.split(":")[-1])
            if "mst_ban" not in data:
                data["mst_ban"] = value
            else:
                data["mst_mua"] = value
        
        elif "Địa chỉ (Address):" in line:
            full_value = line.split(":", 1)[-1]
            address = full_value
            # Tách các trường bị dính liền
            if "Điện thoại (Tel):" in full_value:
                address = full_value.split("Điện thoại (Tel):")[0]
            
            value = clean_text(address)
            # Phân biệt địa chỉ bên bán và bên mua dựa vào nội dung
            if ("Tầng 6" in value or "Tầng 6" in line) and "dia_chi_ban" not in data:
                data["dia_chi_ban"] = value
            else:
                data["dia_chi_mua"] = value

        elif "Điện thoại (Tel):" in line and "dien_thoai" not in data:
            full_value = line.split(":", 1)[-1]
            phone = full_value.split("Số tài khoản")[0]
            data["dien_thoai"] = clean_text(phone)

        elif "Số tài khoản (Bank account):" in line and "so_tai_khoan" not in data:
            full_value = line.split(":", 1)[-1]
            account_info = full_value.split("HÓA ĐƠN GIÁ TRỊ GIA TĂNG")[0]
            parts = account_info.split('-', 1)
            data['so_tai_khoan'] = clean_text(parts[0])
            data['ngan_hang'] = clean_text(parts[1]) if len(parts) > 1 else ""

        elif "Ký hiệu (Serial):" in line and "ky_hieu" not in data:
            match = re.search(r"Ký hiệu \(Serial\):\s*([A-Z0-9]+)", line)
            if match: data["ky_hieu"] = match.group(1)

        elif "Số (No.):" in line and "so_hoa_don" not in data:
            match = re.search(r"Số \(No\.\):\s*(\d+)", line)
            if match: data["so_hoa_don"] = match.group(1)

        elif "Ngày (Date)" in line and "Ngày" not in data:
            match = re.search(r"(\d{2})\s*tháng\s*\(month\)\s*(\d{2})\s*năm\s*\(year\)\s*(\d{4})", line)
            if match: data["Ngày"], data["Tháng"], data["Năm"] = match.groups()
        
        elif "Mã CQT (Code):" in line and "ma_cqt" not in data:
             data["ma_cqt"] = clean_text(line.split(":")[-1])

        elif "Tên đơn vị (Company's name):" in line and "ten_cong_ty_mua" not in data:
             data["ten_cong_ty_mua"] = clean_text(line.split(":")[-1])
        
        elif "Hình thức thanh toán (Payment method):" in line and "hinh_thuc_thanh_toan" not in data:
             data["hinh_thuc_thanh_toan"] = clean_text(line.split(":")[-1])
        
        elif "Cộng tiền hàng (Total amount excl. VAT):" in line and "cong_tien_hang" not in data:
             data["cong_tien_hang"] = clean_text(line.split(":")[-1])
        
        elif "Thuế suất GTGT (VAT rate):" in line and "thue_suat_gtgt" not in data:
             match_rate = re.search(r'(\d+%)', line)
             if match_rate: data["thue_suat_gtgt"] = match_rate.group(1)
             match_amount = re.search(r"Tiền thuế GTGT \(VAT amount\):\s*([\d.,]+)", line)
             if match_amount: data["tien_thue_gtgt"] = match_amount.group(1)

        elif "Tổng tiền thanh toán (Total amount):" in line and "tong_tien_thanh_toan" not in data:
             data["tong_tien_thanh_toan"] = clean_text(line.split(":")[-1])

        elif "Số tiền viết bằng chữ (Total amount in words):" in line and "so_tien_bang_chu" not in data:
             data["so_tien_bang_chu"] = clean_text(line.split(":")[-1]).replace(".", "")
        
        elif "Ký bởi (Signed By):" in line and "ky_boi" not in data:
             data["ky_boi"] = clean_text(line.split(":")[-1])
        
        elif "Ký ngày (Signing Date):" in line and "ky_ngay" not in data:
             data["ky_ngay"] = clean_text(line.split(":")[-1])

        elif "Mã tra cứu (Invoice code):" in line and "ma_tra_cuu" not in data:
             data["ma_tra_cuu"] = clean_text(line.split(":")[-1])

    # --- Xử lý đặc biệt cho chi tiết hàng hóa ---
    try:
        amount_str = data.get("cong_tien_hang")
        block_match = re.search(r"\(Amount\)(.*?)\s*Cộng tiền hàng", text, re.DOTALL)
        if amount_str and block_match:
            messy_block = block_match.group(1).strip()
            
            stt_match = re.search(r"^\s*(\d+)", messy_block)
            stt = stt_match.group(1) if stt_match else "1"
            
            # --- LOGIC LÀM SẠCH ĐÃ SỬA LỖI ---
            # Bắt đầu với toàn bộ khối văn bản lộn xộn
            description = messy_block
            
            # Bước 1: Chỉ loại bỏ chính xác chuỗi số tiền đã biết
            description = description.replace(amount_str, "")

            # Bước 2: Loại bỏ số STT ở đầu chuỗi
            description = re.sub(r"^\s*\d+\s*", "", description)
            
            # Bước 3: Sửa các lỗi văn bản cụ thể nếu có
            description = re.sub(r'\(đợt\s*\d+\s*(\d+)\)', r'(đợt \1)', description)
            
            # Gán kết quả đã được làm sạch
            data['chi_tiet_hang_hoa'] = [{
                "STT": clean_text(stt),
                "Tên Hàng hóa, dịch vụ": clean_text(description),
                "Thành tiền (VND)": clean_text(amount_str)
            }]
    except Exception:
        data['chi_tiet_hang_hoa'] = None
        
    return data


# --- Giao diện ứng dụng Streamlit ---
st.set_page_config(layout="wide", page_title="Trích xuất Hóa đơn PDF")
st.title("📄 Trình trích xuất Hóa đơn PDF (Phiên bản xử lý từng dòng)")
uploaded_file = st.file_uploader("Tải file PDF của bạn tại đây", type="pdf")

if uploaded_file is not None:
    full_text = ""
    with st.spinner('Đang đọc file PDF...'):
        try:
            with pdfplumber.open(uploaded_file) as pdf:
                for page in pdf.pages:
                    full_text += (page.extract_text(x_tolerance=2, y_tolerance=2) or "") + "\n"
        except Exception as e:
            st.error(f"Không thể đọc file PDF. Lỗi: {e}"); st.stop()

    with st.expander("Xem văn bản gốc được trích xuất từ PDF"):
        st.text_area("Văn bản gốc:", full_text, height=300)

    st.markdown("---"); st.header("Kết quả phân tích tự động")
    
    if full_text:
        with st.spinner("Đang phân tích dữ liệu..."):
            data = parse_invoice_data(full_text)
            
            all_keys = ['so_hoa_don', 'ky_hieu', 'Ngày', 'Tháng', 'Năm', 'ma_cqt', 'ten_cong_ty_ban', 'mst_ban', 'dia_chi_ban', 'dien_thoai', 'so_tai_khoan', 'ngan_hang', 'ten_cong_ty_mua', 'ten_nguoi_mua', 'mst_mua', 'dia_chi_mua', 'hinh_thuc_thanh_toan', 'cong_tien_hang', 'thue_suat_gtgt', 'tien_thue_gtgt', 'tong_tien_thanh_toan', 'so_tien_bang_chu', 'ky_boi', 'ky_ngay', 'ma_tra_cuu']
            for key in all_keys: data.setdefault(key, 'N/A')

            if data.get('so_hoa_don') == 'N/A' or not data.get('so_hoa_don'):
                 st.error("Không thể trích xuất thông tin cơ bản. Vui lòng kiểm tra văn bản gốc ở trên.")
            else:
                st.success('Trích xuất thành công!')
                with st.container(border=True):
                    st.subheader("1. Thông tin chung Hóa đơn"); col1, col2, col3, col4 = st.columns(4)
                    col1.text(f"Số hóa đơn: {data['so_hoa_don']}"); col2.text(f"Ký hiệu: {data['ky_hieu']}")
                    ngay_thang_nam = f"{data['Ngày']}/{data['Tháng']}/{data['Năm']}"
                    col3.text(f"Ngày, tháng, năm: {ngay_thang_nam}"); col4.text(f"Mã CQT: {data['ma_cqt']}")
                with st.container(border=True):
                    st.subheader("2. Thông tin các bên"); col_ban, col_mua = st.columns(2)
                    with col_ban:
                        st.markdown("**Bên Bán**"); st.text(f"Tên công ty: {data['ten_cong_ty_ban']}"); st.text(f"Mã số thuế: {data['mst_ban']}"); st.text(f"Địa chỉ: {data['dia_chi_ban']}"); st.text(f"Điện thoại: {data['dien_thoai']}"); st.text(f"Tài khoản: {data.get('so_tai_khoan', '')} tại {data.get('ngan_hang', '')}")
                    with col_mua:
                        st.markdown("**Bên Mua**"); st.text(f"Tên công ty: {data['ten_cong_ty_mua']}"); st.text(f"Họ tên người mua: {data.get('ten_nguoi_mua') or '(Không có)'}"); st.text(f"Mã số thuế: {data['mst_mua']}"); st.text(f"Địa chỉ: {data['dia_chi_mua']}"); st.text(f"Hình thức thanh toán: {data['hinh_thuc_thanh_toan']}")
                with st.container(border=True):
                    st.subheader("3. Chi tiết hàng hóa, dịch vụ")
                    if data.get('chi_tiet_hang_hoa'): st.table(pd.DataFrame(data['chi_tiet_hang_hoa']))
                    else: st.error("Không phân tích được bảng chi tiết hàng hóa.")
                with st.container(border=True):
                    st.subheader("4. Tổng cộng thanh toán"); col_sum_1, col_sum_2 = st.columns(2)
                    with col_sum_1:
                        st.text(f"Cộng tiền hàng (chưa VAT): {data['cong_tien_hang']}"); st.text(f"Thuế suất GTGT: {data['thue_suat_gtgt']}"); st.text(f"Tiền thuế GTGT: {data['tien_thue_gtgt']}"); st.success(f"Tổng tiền thanh toán: {data['tong_tien_thanh_toan']}")
                    with col_sum_2:
                        st.markdown("**Số tiền viết bằng chữ:**"); st.info(f"{data.get('so_tien_bang_chu', 'N/A')}.")
                with st.container(border=True):
                    st.subheader("5. Thông tin Chữ ký và Tra cứu"); col_sign_1, col_sign_2, col_sign_3 = st.columns(3)
                    col_sign_1.text(f"Ký bởi: {data['ky_boi']}"); col_sign_2.text(f"Ngày ký: {data['ky_ngay']}"); col_sign_3.text(f"Mã tra cứu: {data['ma_tra_cuu']}")