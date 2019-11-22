# Copyright (c) 2019 by CEA
#
# The full license specifying the redistribution, modification, usage and other
# rights and obligations is included with the distribution of this project in
# the file "LICENSE".
#
# THIS SOFTWARE IS PROVIDED AS-IS WITHOUT WARRANTY OF ANY KIND, NOT EVEN THE
# IMPLIED WARRANTY OF MERCHANTABILITY. THE AUTHOR OF THIS SOFTWARE, ASSUMES
# _NO_ RESPONSIBILITY FOR ANY CONSEQUENCE RESULTING FROM THE USE, MODIFICATION,
# OR REDISTRIBUTION OF THIS SOFTWARE.

from setuptools import setup, find_packages

# solution coming from: https://stackoverflow.com/questions/25192794/no-module-named-pip-req
try: # for pip >= 10
    from pip._internal.req import parse_requirements
except ImportError: # for pip <= 9.0.3
    from pip.req import parse_requirements

# Solution comming from:
# https://stackoverflow.com/questions/14399534/reference-requirements-txt-for-the-install-requires-kwarg-in-setuptools-setup-py
# TODO: Find a better way to handle this (can stop working at any moment)
install_reqs = parse_requirements('requirements.txt', session='hack')
reqs = [str(ir.req) for ir in install_reqs]


def readme():
    with open('README.md') as f:
        return f.read()


setup(name='wetest',
      version='1.2.0',
      description='WeTest allows you to test EPICS modules',
      long_description=readme(),
      classifiers=[
        'Development Status :: 3 - Alpha',
        'Programming Language :: Python :: 2.7',
      ],
      keywords='epics testing',
      packages=find_packages(),
      package_data={
          'wetest': ['resources/*', 'resources/icons/*', 'resources/logo/*']
      },
      install_requires=reqs,
      entry_points={
        'console_scripts': ['wetest=wetest.command_line:main'],
      },
      zip_safe=False)
