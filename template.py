# -*- coding: utf-8 -*-
"""
    flango.template
    ~~~~~~~~~~~~~~

    template module provide a simple template system that compiles
    templates to Python code which like django and tornado template
    modules.

    Usage
    -----

    Well, you can view the tests file directly for the usage under tests.

    Basically::

            >>> import template
            >>> template.Template('Hello, {{ name }}').render(name='flango')
            Hello, flango

    If, else, for...::

            >>> template.Template('''
            ... {% for i in l %}
            ...    {% if i > 3 %}
            ...    	{{ i }}
            ...    {% else %}
            ... 	less than 3
            ...    {% endif %}
            ... {% endfor %})
            ... ''' ).render(l=[2, 4])
            less than 3
            4

    Then, user define class object maybe also works well::

            >>> class A(object):
            ...
            ...    def __init__(self, a, b):
            ...        self.a = a
            ...        self.b = b
            ...
            >>> o = A("I am o.a", [1, 2, 3])
            >>> template.Template('''
            ...    {{ o.a }}
            ...    {% for i in o.b %}
            ...    	{{ i }}
            ...    {% endfor %}
            ... ''').render(o=o)
            I am o.a
            1
            2
            3

    and Wow, function maybe suprise you::

            >>> template.Template('{{ abs(-3) }}').render()
            '3'
            >>> template.Template('{{ len([1, 2, 3]) }}').render()
            '3'
            >>> template.Template('{{ [1, 2, 3].index(2) }}').render()
            '1'

    and complex function like lambda expression maybe works::

            >>> template.Template('{{ list(map(lambda x: x * 2, [1, 2, 3])) }}').render()
            '[2, 4, 6]'

    and lastly, inheritance of template, extends and include::

            {% extends 'base.html' %}
            {% include 'included.html' %}

    Hacking with fun and joy.

"""
import re
import os
import collections


# LRU Cache capacity:
_CACHE_CAPACITY = 128


class Scanner(object):
    """ Scanner is a inner class of Template which provide
    custom template source reading operations.
    """
    def __init__(self, source):
        # pattern for variable, function, block, statement.
        self.pattern = re.compile(r'''
            {{\s*(?P<var>.+?)\s*}}  # variable: {{ name }} or function like: {{ abs(-2) }}
            |  # or
            {%\s*(?P<endtag>end(if|for|while|block))\s*%}  # endtag: {% endfor %}
            |  # or
            {%\s*(?P<statement>(?P<keyword>\w+)\s*(.+?))\s*%}  # statement: {% for i in range(10) %}
            ''', re.VERBOSE)
        # the pre-text before token.
        self.pretext = ''
        # the remaining text which have not been processed.
        self.remain = source

    def next_token(self):
        """ Get the next token which match the pattern semantic.
        return `None` if there is no more tokens, otherwise,
        return matched regular expression group of token `t`, get
        the pre-text and the remain text at the same time.
        """
        t = self.pattern.search(self.remain)
        if not t:
            return None

        self.pretext = self.remain[:t.start()]
        self.remain = self.remain[t.end():]
        return t

    @property
    def empty(self):
        """ Return `True` if the source have been processed."""
        return self.remain == ''


class BaseNode(object):
    """ Base abstract class for nodes.

    Subclass of BaseNode must implement 'generate' interface for
    output Python intermediate code generating.
    """
    def __init__(self, text, indent, block):
        self.text = text
        self.indent = indent
        self.block = block

    def generate(self):
        raise NotImplementedError()


class TextNode(BaseNode):
    """ Node for normal text. """
    def generate(self):
        return '{0}_stdout.append(\'\'\'{1}\'\'\')\n'.format(' '*self.indent, self.text)


class VariableNode(BaseNode):
    """ Node for variables: such as {{ name }}. """
    def generate(self):
        return '{0}_stdout.append({1})\n'.format(' '*self.indent, self.text)


class KeyNode(BaseNode):
    """ Node for keywords like if else... """
    def generate(self):
        return '{0}{1}\n'.format(' '*self.indent, self.text)


class TemplateException(Exception):
    pass


class Template(object):
    """ Main class for compiled template instance.

    A initialized template instance will parse and compile
    all the template source to Python intermediate code,
    and instance function `render` will use Python builtin function
    `exec` to execute the intermediate code in Python
    runtime.

    As function `exec` own very strong power and the ability to
    execute all the python code in the runtime with given
    namespace dict, so this template engine can perform all
    the python features even lambda function. But, function
    `exec` also has a huge problem in security, so be careful
    and be serious, and I am very serious too.
    """
    def __init__(self, source, path='', autoescape=False):
        if not source:
            raise ValueError('Invalid parameter')

        self.scanner = Scanner(source)
        # path for extends and include
        self.path = path
        self.nodes = []
        # parent template
        self.parent = None
        self.autoescape = autoescape

        self._parse()
        # compiled intermediate code.
        self.intermediate = self._compile()

    def _parse(self):
        python_keywords = ['if', 'for', 'while', 'try', 'else', 'elif', 'except', 'finally']
        indent = 0
        block_stack = []

        def block_stack_top():
            return block_stack[-1] if block_stack else None

        while not self.scanner.empty:
            token = self.scanner.next_token()
            if not token:
                self.nodes.append(TextNode(self.scanner.remain, indent, block_stack_top()))
                break
            # get the pre-text before token.
            if self.scanner.pretext:
                self.nodes.append(TextNode(self.scanner.pretext, indent, block_stack_top()))

            variable, endtag, tag, statement, keyword, suffix = token.groups()
            if variable:
                node_text = 'escape(str({0}))'.format(variable) if self.autoescape else variable
                self.nodes.append(VariableNode(node_text, indent, block_stack_top()))
            elif endtag:
                if tag != 'block':
                    indent -= 1
                    continue
                # block placeholder in parent template nodes
                if not self.parent:
                    node_text = 'endblock%{0}'.format(block_stack_top())
                    self.nodes.append(KeyNode(node_text, indent, block_stack_top()))
                block_stack.pop()
            elif statement:
                if keyword == 'include':
                    filename = re.sub(r'\'|\"', '', suffix)
                    nodes = Loader(self.path).load(filename).nodes
                    for node in nodes:
                        node.indent += indent
                    self.nodes.extend(nodes)
                elif keyword == 'extends':
                    if self.nodes:
                        raise TemplateException('Template syntax error: extends tag must be '
                                                'at the beginning of the file.')
                    filename = re.sub(r'\'|\"', '', suffix)
                    self.parent = Loader(self.path).load(filename)
                elif keyword == 'block':
                    block_stack.append(suffix)
                    if not self.parent:
                        node_text = 'block%{0}'.format(suffix)
                        self.nodes.append(KeyNode(node_text, indent, block_stack_top()))
                elif keyword in python_keywords:
                    node_text = '{0}:'.format(statement)
                    if keyword in ['else', 'elif', 'except', 'finally']:
                        key_indent = indent - 1
                    else:
                        key_indent = indent
                        indent += 1

                    self.nodes.append(KeyNode(node_text, key_indent, block_stack_top()))
                else:
                    raise TemplateException('Invalid keyword: {0}.'.format(keyword))
            else:
                raise TemplateException('Template syntax error.')

    def _compile(self):
        block = {}

        if self.parent:
            generate_code = ''.join(node.generate() for node in self.parent.nodes)
            pattern = re.compile(r'block%(?P<start_block>\w+)(?P<block_code>.*?)endblock%(?P<end_block>\w+)', re.S)
            for node in self.nodes:
                block.setdefault(node.block, []).append(node.generate())

            for token in pattern.finditer(generate_code):
                block_name = token.group('start_block')
                if block_name != token.group('end_block'):
                    raise TemplateException('Template syntax error.')

                block_code = ''.join(block[block_name]) if block_name in block.keys() else token.group('block_code')
                generate_code = generate_code.replace(token.group(), block_code)
        else:
            generate_code = ''.join(node.generate() for node in self.nodes)

        return compile(generate_code, '<string>', 'exec')

    def render(self, **context):
        # `context['_stdout']`: Compiled template source code
        # which is a Python list, contain all the output
        # statement of Python code.
        context.update({'_stdout': [], 'escape': escape})

        exec(self.intermediate, context)
        return re.sub(r'(\s+\n)+', r'\n', ''.join(map(str, context['_stdout'])))


class LRUCache(object):
    """ Simple LRU cache for template instance caching.
    in fact, the OrderedDict in collections module or
    @functools.lru_cache is working well too.
    """
    def __init__(self, capacity):
        self.capacity = capacity
        self.cache = collections.OrderedDict()

    def get(self, key):
        """ Return -1 if catched KeyError exception."""
        try:
            value = self.cache.pop(key)
            self.cache[key] = value
            return value
        except KeyError:
            return -1

    def set(self, key, value):
        try:
            self.cache.pop(key)
        except KeyError:
            if len(self.cache) >= self.capacity:
                self.cache.popitem(last=False)

        self.cache[key] = value


class Loader(object):
    """ A template Loader which loads the environments of
    main application, or just give the template system a root
    directory to search the template files.

        loader = template.Loader("home/to/root/of/templates/")
        loader.load("index.html").render()

    Loader class use a LRU cache system to cache the recently used
    templates for performance consideration.
    """
    def __init__(self, path='', engine=Template, cache_capacity=_CACHE_CAPACITY):
        self.path = path
        self.engine = engine
        self.cache = LRUCache(capacity=cache_capacity)

    def load(self, filename):
        if not self.path.endswith(os.sep) and self.path != '':
            self.path = self.path + os.sep

        p = ''.join([self.path, filename])

        cache_instance = self.cache.get(p)
        if cache_instance != -1:
            return cache_instance

        if not os.path.isfile(p):
            raise TemplateException('Template file {0} is not exist.'.format(p))

        with open(p) as f:
            self.cache.set(p, self.engine(f.read(), path=self.path))

        return self.cache.get(p)


def escape(content):
    """ Escapes a string's HTML. """
    return content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')\
        .replace('"', '&quot;').replace("'", '&#039;')
