library ieee;
use ieee.std_logic_1164.all;

entity no_messages is
    generic (
        DIVIDER : integer := 10
    );
    port (
        reset : in std_logic;
        clk_input : in  std_logic;
        clk_output : out std_logic
    );

end no_messages;

architecture no_messages of no_messages is

begin

end no_messages;
