library ieee;
    use ieee.std_logic_1164.all;
    use ieee.numeric_std.all;

library basic_library;
    use basic_library.very_common_pkg.all;

use work.package_with_constants;

entity clock_divider is
    generic (
        DIVIDER : integer := 10
    );
    port (
        reset : in std_logic;
        clk_input : in  std_logic;
        clk_output : out std_logic
    );

end clock_divider;

architecture clock_divider of clock_divider is

    signal counter      : integer range 0 to DIVIDER - 1 := 0;
    signal clk_internal : std_logic := '0';

    signal clk_enable_unused : std_logic := '0';

begin

    clk_output <= clk_internal;

    useless_u : clk_en_generator
        generic map (
            DIVIDER => DIVIDER)
        port map (
            reset     => reset,
            clk_input => clk_input,
            clk_en    => open);

    -- We read 'reset' signal asynchronously inside the process to force
    -- msim issuing a synthesis warning
    process(clk_input)          
    begin                       
        if reset = '1' then     
            counter <= 0;
        elsif clk_input'event and clk_input = '1' then
            if counter < DIVIDER then
                counter <= counter + 1;
            else
                counter <= 0;
                clk_internal <= not clk_internal;
            end if;
        end if;
    end process;


end clock_divider;


