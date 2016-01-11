Template
========
Template module provide a simple template system that compiles
templates to Python code which like django and tornado template
modules.

Usage
-----

Well, you can view the tests file directly for the usage under tests.

Basically:

    import template
    template.Template('Hello, {{ name }}').render(name='flango')
    Out: Hello, flango

If, else, for...:

    template.Template('''
    {% for i in l %}
        {% if i > 3 %}
        	{{ i }}
        {% else %}
     	less than 3
        {% endif %}
    {% endfor %})
    ''' ).render(l=[2, 4])
    Out:
    less than 3
    4

Then, user define class object maybe also works well:

    class A(object):
       def __init__(self, a, b):
           self.a = a
           self.b = b
    o = A("I am o.a", [1, 2, 3])
    template.Template('''
       {{ o.a }}
       {% for i in o.b %}
       	{{ i }}
       {% endfor %}
    ''').render(o=o)
    Out:
    I am o.a
    1
    2
    3

and function maybe suprise you:

    template.Template('{{ abs(-3) }}').render()
    Out: '3'
    template.Template('{{ len([1, 2, 3]) }}').render()
    Out: '3'
    template.Template('{{ [1, 2, 3].index(2) }}').render()
    Out: '1'

and complex function like lambda expression maybe works:

    template.Template('{{ list(map(lambda x: x * 2, [1, 2, 3])) }}').render()
    Out: '[2, 4, 6]'

and lastly, inheritance of template, extends and include:

    {% extends 'base.html' %}
    {% include 'included.html' %}