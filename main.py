from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import FileResponse, JSONResponse
import qrcode
import fitz  # PyMuPDF
import httpx
from io import BytesIO
import os
from dotenv import load_dotenv
from supabase import create_client, Client
import aiofiles
import re
import tempfile
from fastapi.staticfiles import StaticFiles
import uvicorn


# Supabase yapılandırma bilgileri
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_BUCKET = os.environ.get("SUPABASE_BUCKET")

# Supabase istemcisini oluştur
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# Supabase'e dosya yükleme fonksiyonu
async def upload_to_supabase(file_path: str, file_name: str):
    try:
        async with aiofiles.open(file_path, "rb") as file:
            file_content = await file.read()
            upload_response = supabase.storage.from_(SUPABASE_BUCKET).upload(file_name, file_content, {"content-type": "application/pdf"})
            if not upload_response:
                raise HTTPException(status_code=500, detail="Dosya yükleme başarısız.")  # Daha anlamlı bir hata mesajı
            return upload_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Supabase'e yükleme hatası: {str(e)}")


class QRMaker:
    def __init__(self, qr_code_url):
        self.qr_code_url = qr_code_url
        self.qr = qrcode.QRCode(
            version=3,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=12,
            border=1,
        )

    def create_qr(self):
        """Create a QR code and return it as a PNG image."""
        self.qr.add_data(self.qr_code_url)
        self.qr.make(fit=True)
        img = self.qr.make_image(fill_color="#002147", back_color="white")
        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing special characters."""
    translation_table = str.maketrans("şçöğüıŞÇÖĞÜİ", "scoguiSCOGUI")
    sanitized = filename.translate(translation_table)
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', sanitized).lower()


@app.post("/upload-pdf/")
async def upload_pdf(qr_code_url: str, club_name: str, logo_url: str):
    try:
        qr_maker = QRMaker(qr_code_url)
        qr_image = qr_maker.create_qr()

        # PDF'i aç
        pdf_path = os.path.join(os.getcwd(), "template.pdf")
        pdf_document = fitz.open(pdf_path)

        page = pdf_document[0]  # 1. sayfa için

        # Metin Kutusu Ekleme
        logo_size_in_fitz = 42 * 2.83465
        x_mm_to_fitz = 16 * 2.83465
        y_mm_to_fitz = (162.26 * 2.83465)
        x0 = ((58) * 2.83465) + 25
        x1 = (210 * 2.83465) - x_mm_to_fitz
        rect = fitz.Rect(x0, y_mm_to_fitz + (42 * 2.83465) / 4.5, x1, y_mm_to_fitz + logo_size_in_fitz + (42 * 2.83465) / 4.5)

        font_path = os.path.join("Montserrat-SemiBold.ttf")
        if not os.path.exists(font_path):
            raise HTTPException(status_code=500, detail=f"Font dosyası bulunamadı: {font_path}")

        # Metni ekle
        page.insert_textbox(rect, club_name, fontsize=32, color=(1, 1, 1), fontname="Montserrat-SemiBold", fontfile=font_path, align=1)

        # Logo dosyasını indirme
        async with httpx.AsyncClient() as client:
            response = await client.get(logo_url)
            response.raise_for_status()  # Hata durumunda istisna fırlat
            logo_data = response.content

        # Logo ekleme
        image_rect = fitz.Rect(x_mm_to_fitz + 12, y_mm_to_fitz, x_mm_to_fitz + logo_size_in_fitz - 12, y_mm_to_fitz + logo_size_in_fitz)
        page.insert_image(image_rect, stream=logo_data)

        # QR kodu ekleme
        qr_image_rect = fitz.Rect(155, 75, 440, 355)
        page.insert_image(qr_image_rect, stream=qr_image.read())

        # PDF'i geçici dosyaya kaydet
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            pdf_document.save(temp_file.name)
            pdf_document.close()

        # Supabase'e yükle
        await upload_to_supabase(temp_file.name, sanitize_filename(club_name) + ".pdf")

        # Geçici dosyayı sil
        os.remove(temp_file.name)
        
        return JSONResponse(content={"message": f"{sanitize_filename(club_name)}.pdf başarıyla Supabase'e yüklendi."})

    except HTTPException as http_ex:
        raise http_ex
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    return {"message": "Welcome to the FastAPI application!"}

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("static/favicon.ico")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)