#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    sys.exit()


with open(os.path.join(os.path.dirname(__file__), 'README.md')) as f:
    readme = f.read()

packages = [
    'leds',
]

package_data = {
}

requires = [
    'webcolors',
    'paho-mqtt',
]

classifiers = [
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
]

setup(
    name='leds',
    version='0.0.1',
    description='',
    long_description=readme,
    modules=['leds.py'],
    install_requires=requires,
    author='Kit Barnes',
    author_email='k.barnes@mhnltd.co.uk',
    license='MIT',
    classifiers=classifiers,
)
