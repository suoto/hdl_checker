# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.
"hdlcc installation script"

import setuptools
import versioneer

LONG_DESCRIPTION = open("README.md", "r").read()

# pylint: disable=bad-whitespace
setuptools.setup(
    name                          = 'hdlcc',
    version                       = versioneer.get_version(),
    description                   = 'HDL code checker',
    long_description              = LONG_DESCRIPTION,
    long_description_content_type = "text/markdown",
    author                        = 'Andre Souto',
    author_email                  = 'andre820@gmail.com',
    url                           = 'https://github.com/suoto/hdlcc',
    license                       = 'GPLv3',
    packages                      = setuptools.find_packages(),
    install_requires              = ['argcomplete',
                                     'argparse',
                                     'bottle>=0.12.9',
                                     'waitress>=0.9.0',
                                     'prettytable',
                                     'requests==2.20.0',
                                     'future>=0.14.0',
                                     'futures; python_version<"3.2"',
                                     'python-language-server>=0.26.1',
                                     'backports.functools_lru_cache; python_version<"3.2"',],
    cmdclass                      = versioneer.get_cmdclass(),
    entry_points                  = {
        'console_scripts' : ['hdlcc=hdlcc.standalone:main',]
    }
)
# pylint: enable=bad-whitespace
