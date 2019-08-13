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

