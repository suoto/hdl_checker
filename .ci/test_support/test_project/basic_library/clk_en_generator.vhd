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

use work.very_common_pkg.all;

entity clk_en_generator is
    generic (
        DIVIDER : integer := 10
    );
    port (
        reset     : in std_logic;
        clk_input : in  std_logic;
        clk_en    : out std_logic
    );

end clk_en_generator;

architecture clk_en_generator of clk_en_generator is

    signal clk_divided  : std_logic;
    signal clk_divided0 : std_logic;

begin

    clk_divider_u : clock_divider
        generic map (
            DIVIDER => DIVIDER
        )
        port map (
            reset      => reset,
            clk_input  => clk_input,
            clk_output => clk_divided
        );

    process(clk_input)
    begin
        if clk_input'event and clk_input = '1' then
            clk_divided0 <= clk_divided0;

            clk_en <= '0';
            if clk_divided = '1' and clk_divided0 = '0' then
                clk_en <= '1';
            end if;

            if reset = '1' then
                clk_en <= '0';
            end if;
        end if;
    end process;

end clk_en_generator;

