# create_logo.py - Save this in your main project folder
from PIL import Image, ImageDraw, ImageFont
import os


def create_zcas_logo():
    # Create image with ZCAS blue background
    img_width, img_height = 400, 200
    image = Image.new('RGB', (img_width, img_height),
                      color='#1E3A8A')  # ZCAS blue
    draw = ImageDraw.Draw(image)

    try:
        # Try to use system fonts (common on Windows)
        font_large = ImageFont.truetype("arialbd.ttf", 36)  # Bold Arial
        font_small = ImageFont.truetype("arial.ttf", 16)    # Regular Arial
    except:
        try:
            # Try another common Windows font
            font_large = ImageFont.truetype(
                "C:\\Windows\\Fonts\\arialbd.ttf", 36)
            font_small = ImageFont.truetype(
                "C:\\Windows\\Fonts\\arial.ttf", 16)
        except:
            # Fallback to default font
            from PIL import ImageFont
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    # Draw ZCAS text (centered)
    draw.text((img_width//2, 60), "ZCAS", fill='white',
              font=font_large, anchor="mm")
    draw.text((img_width//2, 100), "UNIVERSITY",
              fill='white', font=font_large, anchor="mm")
    draw.text((img_width//2, 150), "Aspire, Acquire, Prosper",
              fill='#EFF6FF', font=font_small, anchor="mm")

    # Ensure directory exists
    os.makedirs('static/images', exist_ok=True)

    # Save logo
    logo_path = 'static/images/zcas_logo.png'
    image.save(logo_path)
    print(f"ZCAS logo created successfully at: {logo_path}")
    print("Logo dimensions: 400x200 pixels")
    print("Background color: ZCAS Blue (#1E3A8A)")


if __name__ == "__main__":
    create_zcas_logo()
