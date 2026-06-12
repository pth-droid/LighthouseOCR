import os
import tempfile
import unittest

from PIL import Image

from post_process_dialog import _load_invoice_qimage_with_pillow


class PostProcessImageLoadingTests(unittest.TestCase):
    def test_pillow_fallback_loads_valid_jpeg_as_qimage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = os.path.join(tmpdir, "invoice.jpg")
            Image.new("RGB", (12, 8), color=(240, 240, 240)).save(image_path, "JPEG")

            qimage = _load_invoice_qimage_with_pillow(image_path)

            self.assertFalse(qimage.isNull())
            self.assertEqual(qimage.width(), 12)
            self.assertEqual(qimage.height(), 8)


if __name__ == "__main__":
    unittest.main()
