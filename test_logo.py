# test_logo.py
import os
from PIL import Image


def test_logo():
    logo_path = 'static/images/zcas_logo.png'

    # Check if file exists
    if os.path.exists(logo_path):
        print(f"✓ Logo file found: {logo_path}")

        # Try to open the image
        try:
            img = Image.open(logo_path)
            print(f"✓ Logo opened successfully: {img.size} pixels")
            print(f"✓ Logo format: {img.format}")
            print(f"✓ Logo mode: {img.mode}")
            img.close()
            return True
        except Exception as e:
            print(f"✗ Error opening logo: {e}")
            return False
    else:
        print(f"✗ Logo file not found: {logo_path}")
        return False


if __name__ == "__main__":
    test_logo()
