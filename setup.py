#!/usr/bin/env python

from distutils.core import setup
import py2exe

setup(name='Baudotrss',
      version='3.0',
      description='Baudot teletype RSS reader and messaging system',
      author='John Nagle',
      author_email='nagle@aetherltd.com',
      url='https://www.aetherltd.com',
      package_dir = {'baudotrss': 'messager'},
      package_data={'baudotrss': ['messager/configdefault.cfg']},
      packages=['baudotrss'],
      console=['messager/baudotrss.py'],
     )

