#!/usr/bin/env python
# This file is part of HDL Code Checker.
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

from distutils.core import setup

# pylint: disable=bad-whitespace
setup(
    name             = 'hdlcc',
    version          = '0.1',
    description      = 'HDL code checker',
    author           = 'Andre Souto',
    author_email     = 'andre820@gmail.com',
    url              = 'https://github.com/suoto/hdlcc',
    license          = 'GPLv3',
    packages         = ['hdlcc', 'hdlcc.builders'],
    install_requires = ['argcomplete', 'argparse', 'prettytable',],
    entry_points={
        'console_scripts' : ['hdlcc=hdlcc.standalone:main']
    }
)
# pylint: enable=bad-whitespace

