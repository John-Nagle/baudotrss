#!/usr/bin/env python

from distutils.core import setup

setup(name='Baudotrss',
      version='3.0',
      description='Baudot teletype RSS reader and messaging system',
      author='John Nagle',
      author_email='nagle@aetherltd.com',
      url='https://www.aetherltd.com',
      package_dir = {'baudotrss': 'messager'},
      packages=['baudotrss'],
     )

