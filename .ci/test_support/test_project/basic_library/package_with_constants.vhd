-- This file is part of vim-hdl.
--
-- vim-hdl is free software: you can redistribute it and/or modify
-- it under the terms of the GNU General Public License as published by
-- the Free Software Foundation, either version 3 of the License, or
-- (at your option) any later version.
--
-- vim-hdl is distributed in the hope that it will be useful,
-- but WITHOUT ANY WARRANTY; without even the implied warranty of
-- MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
-- GNU General Public License for more details.
--
-- You should have received a copy of the GNU General Public License
-- along with vim-hdl.  If not, see <http://www.gnu.org/licenses/>.

library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library basic_library;

package package_with_constants is

    constant SOME_INTEGER_CONSTANT : integer := 10;
    constant SOME_STRING_CONSTANT  : string := "Hello";

    constant SOME_STRING : string := basic_library.very_common_pkg.VIM_HDL_VERSION;
end;

-- package body package_with_constants is

-- end package body;
