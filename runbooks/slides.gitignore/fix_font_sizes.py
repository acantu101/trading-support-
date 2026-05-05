"""
Fix font sizes across all trading-support PPTX slide decks.

Changes:
  sz="900"  -> sz="1200"  (9pt  -> 12pt, code blocks and table cells)
  sz="1000" -> sz="1200"  (10pt -> 12pt, tip / callout text)
  sz="1200" -> sz="1400"  (12pt -> 14pt, subtitle / description lines)

Also changes spAutoFit -> noAutofit on the main content text box in each slide
so that expanded content cannot bleed over adjacent tip boxes.
"""

import io
import os
import re
import zipfile

SLIDES_DIR = r"C:\Users\aleja\OneDrive\Desktop\linux\trading-support\runbooks\slides.gitignore\trading-support-slides"

# Font-size substitutions (applied in order — be careful not to double-apply)
SIZE_MAP = [
    ('sz="900"',  'sz="1200"'),
    ('sz="1000"', 'sz="1200"'),
    ('sz="1200"', 'sz="1400"'),   # must come AFTER the two above so those run first
]


def fix_slide_xml(xml: str) -> str:
    """Apply all text-size fixes and spAutoFit -> noAutofit to a slide XML string."""

    # 1. Font-size substitutions – two-pass to avoid chained replacements:
    #    Stamp intermediate tokens first, then finalise.
    xml = xml.replace('sz="900"',  'sz="__1200__"')
    xml = xml.replace('sz="1000"', 'sz="__1200__"')
    xml = xml.replace('sz="1200"', 'sz="__1400__"')   # catches original 1200 AND any leftover

    # Resolve tokens
    xml = xml.replace('sz="__1200__"', 'sz="1200"')
    xml = xml.replace('sz="__1400__"', 'sz="1400"')

    # 2. Prevent main-content text boxes from growing into tip boxes.
    #    We only change spAutoFit -> noAutofit inside large text boxes
    #    (identified by their large cy value >= 4 000 000 EMU).
    #    Strategy: find each <p:sp> block that contains <a:spAutoFit/> AND has
    #    a cx/cy where cy >= 4_000_000 and swap the autofit tag.

    def replace_autofit_in_large_boxes(xml_text: str) -> str:
        def fix_sp(m):
            sp_block = m.group(0)
            cy_match = re.search(r'<a:ext\s+cx="[^"]*"\s+cy="(\d+)"', sp_block)
            if cy_match and int(cy_match.group(1)) >= 4_000_000:
                sp_block = sp_block.replace('<a:spAutoFit/>', '<a:noAutofit/>')
            return sp_block

        return re.sub(r'<p:sp>.*?</p:sp>', fix_sp, xml_text, flags=re.DOTALL)

    xml = replace_autofit_in_large_boxes(xml)

    return xml


def fix_pptx(src_path: str, dst_path: str):
    # Read source into memory first so the file handle is released before we write
    with open(src_path, 'rb') as f:
        src_bytes = f.read()

    buf_in = io.BytesIO(src_bytes)
    buf_out = io.BytesIO()

    with zipfile.ZipFile(buf_in, 'r') as zin:
        with zipfile.ZipFile(buf_out, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                raw = zin.read(info.filename)

                is_slide = (
                    info.filename.startswith('ppt/slides/slide')
                    and info.filename.endswith('.xml')
                    and '_rels' not in info.filename
                )

                if is_slide:
                    text = raw.decode('utf-8')
                    text = fix_slide_xml(text)
                    raw = text.encode('utf-8')

                zout.writestr(info, raw)

    buf_out.seek(0)
    # Write to a temp file, then atomically replace the original
    tmp_path = dst_path + '.tmp'
    with open(tmp_path, 'wb') as f:
        f.write(buf_out.read())
    os.replace(tmp_path, dst_path)


def main():
    import tempfile, shutil

    pptx_files = sorted(
        f for f in os.listdir(SLIDES_DIR) if f.endswith('.pptx')
    )
    out_dir = os.path.join(SLIDES_DIR, "fixed")
    os.makedirs(out_dir, exist_ok=True)
    print(f"Found {len(pptx_files)} PPTX files in {SLIDES_DIR}")
    print(f"Writing fixed files to: {out_dir}\n")

    for fname in pptx_files:
        src = os.path.join(SLIDES_DIR, fname)
        dst = os.path.join(out_dir, fname)

        # Write to a system temp location first, then copy
        with tempfile.NamedTemporaryFile(suffix='.pptx', delete=False) as tmp:
            tmp_path = tmp.name

        try:
            print(f"  Processing {fname} ...", end=" ", flush=True)
            fix_pptx(src, tmp_path)
            shutil.copy2(tmp_path, dst)
            print("done")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    print(f"\nAll {len(pptx_files)} files written to {out_dir}")


if __name__ == "__main__":
    main()
