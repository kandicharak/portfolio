"""
Image to PDF Converter
Scans the current folder for .png and .jpg images and converts them
into a single result.pdf file.
"""

import os
import sys
from PIL import Image


def get_image_files(folder: str = ".") -> list:
    """Return a sorted list of .png and .jpg image paths in the given folder."""
    valid_extensions = (".png", ".jpg", ".jpeg")
    images = []
    for fname in os.listdir(folder):
        if fname.lower().endswith(valid_extensions):
            images.append(os.path.join(folder, fname))
    return sorted(images)


def images_to_pdf(image_paths: list, output_pdf: str = "result.pdf") -> str:
    """
    Convert a list of image paths into a single PDF.
    The first image is used as the base, and the rest are appended.
    Returns the output PDF path.
    """
    if not image_paths:
        raise ValueError("No image files found to convert.")

    pil_images = []
    for path in image_paths:
        try:
            img = Image.open(path)
            # Convert RGBA/P modes to RGB for PDF compatibility
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            pil_images.append(img)
        except Exception as e:
            print(f"  [WARN] Skipping {path}: {e}")

    if not pil_images:
        raise ValueError("No valid images could be opened for conversion.")

    first = pil_images[0]
    rest = pil_images[1:] if len(pil_images) > 1 else None

    if rest:
        first.save(output_pdf, save_all=True, append_images=rest)
    else:
        first.save(output_pdf)

    return output_pdf


def main():
    folder = "."  # current directory
    print(f"Scanning folder: {os.path.abspath(folder)}")
    images = get_image_files(folder)

    if not images:
        print("No .png or .jpg images found in the current folder.")
        sys.exit(1)

    print(f"Found {len(images)} image(s):")
    for img in images:
        print(f"  - {img}")

    try:
        output = images_to_pdf(images)
        print(f"\n[OK] PDF created successfully: {os.path.abspath(output)}")
    except Exception as e:
        print(f"\n[FAIL] Failed to create PDF: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
