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
