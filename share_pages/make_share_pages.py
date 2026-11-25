"""Writes the customer guide pages into the share folder, one copy per shop: <guide>_<shop>.html, served at
https://share.ukrsalon.com.ua/<guide>_<shop>.html. A copy differs only in the shop name, logo and site: {{BRAND}},
{{LOGO}}, {{LOGO_W}}, {{LOGO_H}}, {{SITE}} in the template. Logos are PNG files in <out_dir>/img (put there by hand,
not in git).

    python share_pages/make_share_pages.py [out_dir]

Shop slugs must match constants.PRODUCT_SMS_SHOP_SLUGS, which builds the SMS links.
"""
import html
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(r'E:\Share')
LOGO_DIR = 'img'
GUIDES = ('fusion',)  # template <guide>.html next to this script
SHOPS = {  # slug: (name in the page, logo file in LOGO_DIR, shop site the logo links to)
    'ukrsalon': ('UkrSalon', 'ukrsalon_ukr.png', 'https://ukrsalon.com.ua/'),
    'ukrstil': ('UkrStil', 'ukrstil_ukr.png', 'https://ukrstil.com/ua/'),
    'klimazon': ('Klimazon', 'klimazon_ukr.png', 'https://klimazon.com/'),
    'beauty': ('Beauty Market', 'beauty-market_ukr.png', 'https://beauty-market.com.ua/ua/'),
    'krasunia': ('Krasunia', 'krasunia_ukr.png', 'https://krasunia.com/ua/'),
}


def png_size(path: Path) -> tuple[int, int]:
    """Width and height from the PNG header, set on <img> so the page doesn't jump while the logo loads."""
    header = path.read_bytes()[:24]
    if header[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path} is not a PNG file')
    return struct.unpack('>II', header[16:24])


def main(out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for guide in GUIDES:
        template = (HERE / f'{guide}.html').read_text(encoding='utf-8')
        for slug, (brand, logo, site) in SHOPS.items():
            width, height = png_size(out_dir / LOGO_DIR / logo)
            page_html = (
                template.replace('{{BRAND}}', html.escape(brand))
                .replace('{{SITE}}', html.escape(site))
                .replace('{{LOGO}}', html.escape(logo))
                .replace('{{LOGO_W}}', str(width))
                .replace('{{LOGO_H}}', str(height))
            )
            page = out_dir / f'{guide}_{slug}.html'
            page.write_text(page_html, encoding='utf-8', newline='\n')
            print(page)


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR)
