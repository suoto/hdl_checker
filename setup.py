# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"HDL Checker installation script"

import setuptools  # type: ignore
import versioneer

LONG_DESCRIPTION = open("README.md", "rb").read().decode(encoding='utf8', errors='replace')

CLASSIFIERS = """\
Development Status :: 5 - Production/Stable
Environment :: Console
Intended Audience :: Developers
License :: OSI Approved :: GNU General Public License v3 (GPLv3)
Operating System :: Microsoft :: Windows
Operating System :: POSIX :: Linux
Programming Language :: Python
Programming Language :: Python :: 3
Programming Language :: Python :: 3.5
Programming Language :: Python :: 3.6
Programming Language :: Python :: 3.7
Topic :: Software Development
Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)
Topic :: Text Editors :: Integrated Development Environments (IDE)
"""

# pylint: disable=bad-whitespace
setuptools.setup(
    name                          = 'hdl_checker',
    version                       = versioneer.get_version(),
    description                   = 'HDL code checker',
    long_description              = LONG_DESCRIPTION,
    long_description_content_type = "text/markdown",
    author                        = 'Andre Souto',
    author_email                  = 'andre820@gmail.com',
    url                           = 'https://github.com/suoto/hdl_checker',
    license                       = 'GPLv3',
    keywords                      = 'VHDL Verilog SystemVerilog linter LSP language server protocol vimhdl vim-hdl',
    platforms                     = 'any',
    packages                      = setuptools.find_packages(),
    install_requires              = ['argcomplete',
                                     'argparse',
                                     'backports.functools_lru_cache; python_version<"3.2"',
                                     'bottle>=0.12.9',
                                     'enum34>=1.1.6; python_version<"3.3"',
                                     'future>=0.14.0',
                                     'futures; python_version<"3.2"',
                                     'prettytable>=0.7.2',
                                     'pygls',
                                     'requests>=2.20.0',
                                     'six>=1.10.0',
                                     'tabulate>=0.8.5',
                                     'typing>=3.7.4',
                                     'waitress>=0.9.0', ],
    cmdclass                      = versioneer.get_cmdclass(),
    entry_points                  = {
        'console_scripts' : ['hdl_checker=hdl_checker.server:main', ]
    },
    classifiers=CLASSIFIERS.splitlines(),
)
# pylint: enable=bad-whitespace
