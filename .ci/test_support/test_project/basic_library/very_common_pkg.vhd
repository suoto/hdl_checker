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

package very_common_pkg is
    constant VIM_HDL_VERSION : string := "0.1";

    component clock_divider is
        generic (
            DIVIDER : integer := 10
        );
        port (
            reset : in std_logic;
            clk_input : in  std_logic;
            clk_output : out std_logic
        );
    end component;

    component clk_en_generator is
        generic (
            DIVIDER : integer := 10
        );
        port (
            reset     : in std_logic;
            clk_input : in  std_logic;
            clk_en    : out std_logic
        );

    end component;

end package;

-- package body very_common_pkg is

-- end package body;

