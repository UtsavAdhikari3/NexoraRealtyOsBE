"""Create visual QA contact sheets for rendered DOCX chunk pages."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent / "outputs" / "master_qa_documentation" / "_docx_chunks"
OUT = ROOT / "contact_sheets"
OUT.mkdir(parents=True, exist_ok=True)

pages = []
for chunk_dir in sorted(ROOT.glob("guide_chunk_*_pages")):
    for page in sorted(chunk_dir.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1])):
        pages.append((chunk_dir.name.replace("_pages", ""), page))

font = ImageFont.load_default()
per_sheet = 12
thumb_w, thumb_h = 360, 510
label_h = 22
gap = 18
cols, rows = 4, 3

for sheet_index in range(0, len(pages), per_sheet):
    batch = pages[sheet_index:sheet_index + per_sheet]
    canvas = Image.new("RGB", (gap + cols * (thumb_w + gap), gap + rows * (thumb_h + label_h + gap)), "#CBD5E1")
    draw = ImageDraw.Draw(canvas)
    for index, (chunk, page_path) in enumerate(batch):
        image = Image.open(page_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        col = index % cols
        row = index // cols
        x = gap + col * (thumb_w + gap)
        y = gap + row * (thumb_h + label_h + gap)
        canvas.paste(image, (x + (thumb_w - image.width) // 2, y))
        label = f"{chunk} / {page_path.stem}"
        draw.rectangle((x, y + thumb_h, x + thumb_w, y + thumb_h + label_h), fill="#17324D")
        draw.text((x + 6, y + thumb_h + 5), label, fill="white", font=font)
    out = OUT / f"contact_{sheet_index // per_sheet + 1:02d}.png"
    canvas.save(out)
    print(out)

