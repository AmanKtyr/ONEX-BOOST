from django import template

register = template.Library()

@register.filter(name='attr')
def attr(field, css):
    attrs = {}
    definition = css.split(',')

    has_class = any('class:' in s for s in definition)

    for d in definition:
        if ':' in d:
            key, val = d.split(':', 1)
            if key == 'class' and field.errors:
                val += ' is-invalid'
            attrs[key] = val
        else:
            attrs[d] = ''
    
    if not has_class and field.errors:
        attrs['class'] = 'is-invalid'

    return field.as_widget(attrs=attrs)