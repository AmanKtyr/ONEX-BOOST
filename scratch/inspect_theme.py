with open('Brun Haus Cafe/index.html', 'r', encoding='utf-8', errors='ignore') as f:
    text = f.read()

import re
img_matches = re.findall(r'<div class="image-about-[0-9]"[^>]*>|image-about-[0-9]', text)
print("Image classes in index:", set(img_matches))

# Let's check image-about-1,2,3 in css
with open('static/css/theme-brunhaus.min.css', 'r', encoding='utf-8', errors='ignore') as f:
    css = f.read()

for c in ['image-about-1', 'image-about-2', 'image-about-3', 'image']:
    m = re.search(r'\.' + c + r'\{([^}]+)\}', css)
    if m:
        print(c, m.group(1))
