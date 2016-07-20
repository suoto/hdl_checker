module no_messages (
    input  clk,
    input  rst,
    output foo);

reg foo_i;

assign foo = foo_i;

always @ (posedge clk or posedge rst)
    if (rst == 1'b1) begin
        foo_i <= 0;
    end
    else begin
        foo_i <= !foo_i; 
    end


endmodule

