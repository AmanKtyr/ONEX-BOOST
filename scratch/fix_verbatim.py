import os

target_dir = 'templates/website/brunhaus'
count = 0
for root, dirs, files in os.walk(target_dir):
    for file in files:
        p = os.path.join(root, file)
        try:
            with open(p, 'r', encoding='utf-8') as f:
                c = f.read()
            if '{{' in c:
                c_fixed = c.replace('window.__WEBFLOW_CURRENCY_SETTINGS =', '{% verbatim %}window.__WEBFLOW_CURRENCY_SETTINGS =').replace('hideDecimalForWholeNumbers": false };', 'hideDecimalForWholeNumbers": false };{% endverbatim %}')
                c_fixed = c_fixed.replace('hideDecimalForWholeNumbers":false};', 'hideDecimalForWholeNumbers":false};{% endverbatim %}')
                with open(p, 'w', encoding='utf-8') as f:
                    f.write(c_fixed)
                count += 1
                print('Fixed:', p)
        except Exception as e:
            print('Error on:', p, e)

print(f'Total files fixed: {count}')
