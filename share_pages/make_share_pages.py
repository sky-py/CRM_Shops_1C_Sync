"""Writes the customer guide pages into the share folder, one copy per shop: <guide>_<shop>.html, served at
https://share.ukrsalon.com.ua/<guide>_<shop>.html. A copy differs only in the shop name ({{BRAND}} in the template).

    python share_pages/make_share_pages.py [out_dir]

Shop slugs must match constants.PRODUCT_SMS_SHOP_SLUGS, which builds the SMS links.
"""
import html
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT_DIR = Path(r'E:\Share')
GUIDES = ('fusion',)  # template <guide>.html next to this script
SHOPS = {  # slug: name in the page
    'ukrsalon': 'UkrSalon',
    'ukrstil': 'UkrStil',
    'klimazon': 'Klimazon',
    'beauty': 'Beauty Market',
    'krasunia': 'Krasunia',
}


def main(out_dir: Path = OUT_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for guide in GUIDES:
        template = (HERE / f'{guide}.html').read_text(encoding='utf-8')
        for slug, brand in SHOPS.items():
            page = out_dir / f'{guide}_{slug}.html'
            page.write_text(template.replace('{{BRAND}}', html.escape(brand)), encoding='utf-8', newline='\n')
            print(page)


if __name__ == '__main__':
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR)
