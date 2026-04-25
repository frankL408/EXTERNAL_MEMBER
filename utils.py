from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from PIL import Image
from config import Config


def generate_id_card(member, output_path):
    """Generate PDF ID card for a member"""
    c = canvas.Canvas(output_path, pagesize=(350, 200))

    # Draw background and borders
    c.setFillColorRGB(0.9, 0.9, 0.9)
    c.rect(0, 0, 350, 200, fill=1)
    c.setFillColorRGB(0, 0.2, 0.4)
    c.rect(10, 10, 330, 180, fill=0)

    # Add university header
    c.setFillColorRGB(0, 0.2, 0.4)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(80, 170, "ZCAS UNIVERSITY")
    c.setFont("Helvetica", 12)
    c.drawString(100, 155, "LIBRARY MEMBER ID")

    # Add member photo if exists
    photo_path = os.path.join(Config.UPLOAD_FOLDER, member.picture_filename)
    if os.path.exists(photo_path):
        try:
            img = Image.open(photo_path)
            img.thumbnail((80, 80))
            temp_path = os.path.join(
                Config.UPLOAD_FOLDER, f"temp_{member.picture_filename}")
            img.save(temp_path)
            c.drawImage(temp_path, 30, 90, width=60, height=60)
            os.remove(temp_path)
        except Exception as e:
            print(f"Error processing image: {e}")

    # Add member details
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(110, 130, f"ID: {member.member_id}")
    c.drawString(110, 115, f"Name: {member.full_name}")
    c.drawString(110, 100, f"Stream: {member.stream_type.title()}")
    c.drawString(
        110, 85, f"Valid Until: {member.expiry_date.strftime('%Y-%m-%d')}")

    # Add footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(100, 30, "This card is property of ZCAS University")
    c.drawString(120, 20, "Library Services")

    c.save()
    return output_path
