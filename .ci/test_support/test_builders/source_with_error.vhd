library ieee;
use ieee.std_logic_1164.all;

use some_lib.all; -- The error is here!

entity source_with_error is
    generic (
        DIVIDER : integer := 10
    );
    port (
        reset : in std_logic;
        clk_input : in  std_logic;
        clk_output : out std_logic
    );

end source_with_error;

architecture source_with_error of source_with_error is

begin

end source_with_error;
