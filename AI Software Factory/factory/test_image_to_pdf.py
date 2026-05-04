"""
Test script for image_to_pdf.py
Generates 3 dummy images (PNG, JPG, and a gradient PNG) and then
converts them into a single PDF using image_to_pdf.py.
"""

import os
import sys
from PIL import Image, ImageDraw

# Import the converter
from image_to_pdf import images_to_pdf


def create_dummy_image_png(path: str, text: str, color: tuple):
    """Create a simple PNG image with colored background and text."""
    img = Image.new("RGB", (400, 300), color)
    draw = ImageDraw.Draw(img)
    draw.text((50, 130), text, fill=(255, 255, 255))
    img.save(path)
    print(f"  Created: {path}")


def create_dummy_image_jpg(path: str, text: str, color: tuple):
    """Create a simple JPG image with colored background and text."""
    img = Image.new("RGB", (500, 350), color)
    draw = ImageDraw.Draw(img)
    draw.text((50, 150), text, fill=(255, 255, 255))
    img.save(path, "JPEG")
    print(f"  Created: {path}")


def create_dummy_image_rgba_png(path: str, text: str):
    """Create a PNG image with RGBA (transparency) to test conversion."""
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Draw a semi-transparent circle
    draw.ellipse([50, 50, 250, 250], fill=(0, 150, 255, 200))
    draw.text((60, 130), text, fill=(255, 255, 255))
    img.save(path)
    print(f"  Created: {path}")


def main():
    # ---- Step 1: Generate dummy images -----------------------------------
    print("=" * 60)
    print("STEP 1: Generating 3 dummy images...")
    print("=" * 60)

    test_dir = os.path.dirname(os.path.abspath(__file__))
    images = [
        os.path.join(test_dir, "dummy_red.png"),
        os.path.join(test_dir, "dummy_blue.jpg"),
        os.path.join(test_dir, "dummy_gradient.png"),
    ]

    create_dummy_image_png(images[0], "Page 1 - Red", (200, 50, 50))
    create_dummy_image_jpg(images[1], "Page 2 - Blue", (50, 100, 200))
    create_dummy_image_rgba_png(images[2], "Page 3 - Circle")

    # ---- Step 2: Verify images exist -------------------------------------
    print("\n" + "=" * 60)
    print("STEP 2: Verifying images...")
    print("=" * 60)
    for img_path in images:
        if os.path.exists(img_path):
            size = os.path.getsize(img_path)
            print(f"  [OK] {img_path} ({size} bytes)")
        else:
            print(f"  [FAIL] {img_path} NOT FOUND")
            sys.exit(1)

    # ---- Step 3: Convert to PDF ------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 3: Converting images to PDF...")
    print("=" * 60)

    output_pdf = os.path.join(test_dir, "result.pdf")
    try:
        result = images_to_pdf(images, output_pdf)
        print(f"\n  [OK] PDF created: {result}")
    except Exception as e:
        print(f"\n  [FAIL] Error: {e}")
        sys.exit(1)

    # ---- Step 4: Verify PDF ----------------------------------------------
    print("\n" + "=" * 60)
    print("STEP 4: Verifying PDF...")
    print("=" * 60)
    if os.path.exists(output_pdf):
        size = os.path.getsize(output_pdf)
        print(f"  [OK] PDF exists: {output_pdf} ({size} bytes)")
    else:
        print(f"  [FAIL] PDF not found at {output_pdf}")
        sys.exit(1)

    # ---- Step 5: Cleanup dummy images ------------------------------------
    print("\n" + "=" * 60)
    print("STEP 5: Cleaning up dummy images...")
    print("=" * 60)
    for img_path in images:
        try:
            os.remove(img_path)
            print(f"  Removed: {img_path}")
        except Exception as e:
            print(f"  [WARN] Could not remove {img_path}: {e}")

    print("\n" + "=" * 60)
    print("[PASS] ALL TESTS PASSED! result.pdf is ready.")
    print("=" * 60)


if __name__ == "__main__":
    main()
