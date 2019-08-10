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

entity foo is
    generic (
        DIVIDER_A : integer := 10;
        DIVIDER_B : integer := 20
    );
    port (
        rst_a, clk_in_a : in std_logic;
        clk_out_a : out std_logic;

        rst_b, clk_in_b : in std_logic;
        clk_out_b : out std_logic

    );
end foo;

architecture foo of foo is




    -- A signal declaration that generates a warning
    signal neat_signal : std_logic_vector(DIVIDER_A + DIVIDER_B - 1 downto 0) := (others => '0');

begin

    clk_div_a : entity basic_library.clock_divider
        generic map (
            DIVIDER => DIVIDER_A
        )
        port map (
            reset => rst_a, 
            clk_input => clk_in_a, 
            clk_output => clk_out_a
        );

    clk_div_b : entity basic_library.clock_divider
        generic map (
            DIVIDER => DIVIDER_B
        )
        port map (
            reset => rst_b, 
            clk_input => clk_in_b, 
            clk_output => clk_out_b
        );
    -----------------------------
    -- Asynchronous asignments --
    -----------------------------


end foo;

