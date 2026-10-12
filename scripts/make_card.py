# -*- coding: utf-8 -*-
"""
video-quote-card: 视频截图条 + 字幕文案 -> 竖版金句卡
用法示例:
  python make_card.py --images img1.jpg img2.jpg --text copy.txt --out out.png
  python make_card.py --images shots/ --lines "第一句|第二句" --scrim both --letter-spacing 4 --out out.png
文案文件: 每行一句, 与截图按顺序一一对应(截图不够时循环复用)。

关键样式参数:
  --fit-text / --line-pad   字幕条高度按文字自适应 + 上下留白
  --letter-spacing          字间距(px, 按 1080 宽基准缩放), 默认 3
  --scrim dark|blur|both    文字区压暗 / 背景模糊 / 两者都做, 提升可读性
  --scrim-strength          压暗强度 0~1, 默认 0.4
  --gap                     截图条之间的分隔缝(px), 默认 2
"""
import argparse
import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

DEFAULT_FONT = r"C:\Windows\Fonts\msyhbd.ttc"
FALLBACK_FONTS = [
    # Windows
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]


def find_font():
    if os.path.exists(DEFAULT_FONT):
        return DEFAULT_FONT
    for f in FALLBACK_FONTS:
        if os.path.exists(f):
            return f
    raise SystemExit("未找到中文字体, 请用 --font 指定 ttf/ttc 路径")


def load_lines(args):
    if args.text:
        with open(args.text, "r", encoding="utf-8-sig") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    elif args.lines:
        lines = [ln.strip() for ln in args.lines.split("|") if ln.strip()]
    else:
        raise SystemExit("必须提供 --text 文件或 --lines 文案")
    return lines


def load_images(paths):
    imgs = []
    for p in paths:
        if os.path.isdir(p):
            files = sorted(
                os.path.join(p, f) for f in os.listdir(p)
                if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp"))
            )
            imgs.extend(files)
        else:
            imgs.append(p)
    if not imgs:
        raise SystemExit("未找到任何截图")
    return [Image.open(p).convert("RGB") for p in imgs]


def get_band(img, out_w, band_h, position):
    """把 img 缩放到宽度=out_w, 然后按 position 裁出高度=band_h 的横条"""
    w, h = img.size
    new_h = max(1, round(h * out_w / w))
    im = img.resize((out_w, new_h), Image.LANCZOS)
    if new_h <= band_h:
        canvas = Image.new("RGB", (out_w, band_h), (0, 0, 0))
        canvas.paste(im, (0, (band_h - new_h) // 2))
        return canvas
    if isinstance(position, str) and position.startswith("top:"):
        y = min(int(position.split(":", 1)[1]), new_h - band_h)
    elif position == "top":
        y = 0
    elif position == "bottom":
        y = new_h - band_h
    else:  # center
        y = (new_h - band_h) // 2
    return im.crop((0, y, out_w, y + band_h))


def text_width(draw, text, font, spacing):
    n = len(text)
    if n == 0:
        return 0
    return sum(draw.textlength(c, font=font) for c in text) + spacing * (n - 1)


def text_bbox(draw, text, font, stroke_w):
    return draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)


def fit_font(draw, text, font_path, max_size, max_width, stroke_w, spacing):
    """字号自动缩小直到文字(含描边与字距)不超过 max_width"""
    size = max_size
    while size > 10:
        font = ImageFont.truetype(font_path, size)
        if text_width(draw, text, font, spacing) + 2 * stroke_w <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(font_path, 10)


def apply_scrim(band, y0, y1, mode, strength):
    """在文字区(y0~y1)做背景处理: blur 模糊 / dark 压暗, 边缘渐变过渡"""
    if mode == "none":
        return band
    W, H = band.size
    y0 = max(0, int(y0))
    y1 = min(H, int(y1))
    if y1 <= y0:
        return band
    zone_h = y1 - y0
    fade = max(6, int(zone_h * 0.35))
    mask = Image.new("L", (W, H), 0)
    px = mask.load()
    for y in range(y0, y1):
        d = min(y - y0, y1 - 1 - y)
        a = 1.0 if d >= fade else (d / float(fade))
        v = int(255 * a * (strength if mode in ("dark", "both") else 1.0))
        for x in range(W):
            px[x, y] = v
    out = band
    if mode in ("blur", "both"):
        blurred = out.filter(ImageFilter.GaussianBlur(max(3, zone_h / 9.0)))
        out = Image.composite(blurred, out, mask)
    if mode in ("dark", "both"):
        dark = Image.new("RGB", (W, H), (0, 0, 0))
        m = mask if mode == "dark" else mask.point(lambda v: int(v * 0.85))
        out = Image.composite(dark, out, m)
    return out


def draw_line(img, text, font, stroke_w, spacing, y_top):
    """逐字绘制以支持字间距; y_top 为文字顶部(含描边)位置"""
    draw = ImageDraw.Draw(img)
    W = img.size[0]
    total = text_width(draw, text, font, spacing)
    x = (W - total) / 2.0
    for c in text:
        w = draw.textlength(c, font=font)
        draw.text((x, y_top), c, font=font, fill=(255, 255, 255),
                  stroke_width=stroke_w, stroke_fill=(0, 0, 0))
        x += w + spacing


def soft_shadow(band, text, font, stroke_w, spacing, y_top, strength=0.55, blur=None):
    """文字后方加柔和投影(不压背景): 黑色文字模糊后垫底, 再画白字"""
    W, H = band.size
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    total = text_width(draw, text, font, spacing)
    x = (W - total) / 2.0
    for c in text:
        w = draw.textlength(c, font=font)
        draw.text((x, y_top), c, font=font, fill=(0, 0, 0, 255),
                  stroke_width=stroke_w, stroke_fill=(0, 0, 0, 255))
        x += w + spacing
    radius = blur if blur else max(4, font.size // 5)
    layer = layer.filter(ImageFilter.GaussianBlur(radius))
    if strength < 1.0:
        a = layer.getchannel("A").point(lambda v: int(v * strength))
        layer.putalpha(a)
    band.paste(layer, (0, 0), layer)
    return band


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", nargs="+", required=True, help="截图文件或目录(目录内按文件名排序)")
    ap.add_argument("--text", help="文案文件路径, 每行一句")
    ap.add_argument("--lines", help="直接给文案, 用 | 分隔")
    ap.add_argument("--out", required=True, help="输出图片路径")
    ap.add_argument("--width", type=int, default=1080, help="输出宽度, 默认 1080")
    ap.add_argument("--first-ratio", type=float, default=0.72, help="首条高度/宽度, 默认 0.72")
    ap.add_argument("--strip-ratio", type=float, default=0.13,
                    help="字幕条高度/宽度, 仅 --no-fit-text 时生效")
    ap.add_argument("--font-size", type=int, default=None, help="字号, 默认 宽度/24.5")
    ap.add_argument("--font", default=find_font(), help="字体文件路径")
    ap.add_argument("--crop", choices=["top", "center", "bottom"], default=None,
                    help="裁切位置, 默认第一条 top 其余 center")
    ap.add_argument("--crops", default=None,
                    help="每条的裁切位置, 逗号分隔, 每条格式 top|center|bottom|top:N (N=距顶部像素), "
                         "不足时重复最后一个, 如 'top:340,top:1250,center'")
    ap.add_argument("--no-fit-text", action="store_true",
                    help="关闭字幕条自适应高度, 改用 --strip-ratio 固定高度")
    ap.add_argument("--line-pad", type=float, default=0.42,
                    help="字幕条上下留白, 相对字号的比例, 默认 0.42")
    ap.add_argument("--letter-spacing", type=float, default=3.0,
                    help="字间距(按 1080 宽基准的像素), 默认 3")
    ap.add_argument("--scrim", choices=["shadow", "none", "dark", "blur", "both"], default="shadow",
                    help="文字可读性处理: shadow 柔和投影(默认, 不压背景) / dark 压暗 / blur 模糊 / both / none")
    ap.add_argument("--scrim-strength", type=float, default=0.4, help="压暗强度 0~1, 默认 0.4")
    ap.add_argument("--gap", type=int, default=2, help="截图条之间的分隔缝像素, 默认 2(纯黑)")
    ap.add_argument("--first-text", choices=["center", "bottom"], default="bottom",
                    help="首条文字位置, 默认 bottom 贴底(不压脸)")
    ap.add_argument("--raw", action="store_true", help="不叠加文字, 只拼接截图条")
    ap.add_argument("--stroke", type=int, default=None, help="描边宽度, 默认 字号/9")
    args = ap.parse_args()

    lines = load_lines(args)
    images = load_images(args.images)
    W = args.width
    font_size = args.font_size or max(12, round(W / 24.5))
    stroke_w = args.stroke if args.stroke is not None else max(2, font_size // 9)
    pad = round(font_size * args.line_pad)
    spacing = round(args.letter_spacing * W / 1080.0)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))

    # 预排版: 每条的字号/文字宽度/文字高度/条高
    plans = []
    for i, line in enumerate(lines):
        font = bbox = None
        tw = th = 0
        if not args.raw and line:
            font = fit_font(probe, line, args.font, font_size, W - 60, stroke_w, spacing)
            bbox = text_bbox(probe, line, font, stroke_w)
            tw = text_width(probe, line, font, spacing) + 2 * stroke_w
            th = bbox[3] - bbox[1]
        if i == 0:
            band_h = round(W * args.first_ratio)
        elif args.no_fit_text or args.raw or not line:
            band_h = round(W * args.strip_ratio)
        else:
            band_h = max(60, th + 2 * pad)
        plans.append((font, bbox, tw, th, band_h))

    strips = []
    for i, line in enumerate(lines):
        img = images[i % len(images)]
        font, bbox, tw, th, band_h = plans[i]
        if args.crops:
            parts = [p.strip() for p in args.crops.split(",")]
            pos = parts[i] if i < len(parts) else parts[-1]
        else:
            pos = args.crop or ("top" if i == 0 else "center")
        band = get_band(img, W, band_h, pos)

        if font is not None:
            if i == 0 and args.first_text == "bottom" and band_h > th + 2 * pad:
                y_top = band_h - th - pad - bbox[1]
            else:
                y_top = (band_h - th) // 2 - bbox[1]
            if args.scrim == "shadow":
                band = soft_shadow(band, line, font, stroke_w, spacing, y_top,
                                   strength=args.scrim_strength + 0.15)
            else:
                band = apply_scrim(band, y_top + bbox[1] - pad, y_top + bbox[1] + th + pad,
                                   args.scrim, args.scrim_strength)
            draw_line(band, line, font, stroke_w, spacing, y_top)
        strips.append(band)

    gap = max(0, round(args.gap * W / 1080.0))
    total_h = sum(s.height for s in strips) + gap * (len(strips) - 1)
    out = Image.new("RGB", (W, total_h), (0, 0, 0))
    y = 0
    for s in strips:
        out.paste(s, (0, y))
        y += s.height + gap
    out.save(args.out, quality=95)
    print(f"OK: {args.out}  尺寸 {W}x{total_h}  共 {len(lines)} 条  字号 {font_size}  "
          f"条高 {strips[1].height if len(strips) > 1 else ''}  字距 {spacing}  背景 {args.scrim}")


if __name__ == "__main__":
    main()
