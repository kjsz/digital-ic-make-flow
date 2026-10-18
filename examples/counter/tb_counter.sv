`timescale 1ns/1ps
module tb_counter;
    reg clk = 0;
    reg rst_n = 0;
    wire [3:0] count;
    counter dut(.clk(clk), .rst_n(rst_n), .count(count));
    always #5 clk = ~clk;
    initial begin
        $dumpfile("wave.vcd");
        $dumpvars(0, tb_counter);
        #12; rst_n = 1; // 保证至少一个时钟上升沿处于复位状态
        repeat (3) @(posedge clk);
        #1;
        if (count !== 4'd3) $fatal(1, "counter mismatch");
        $display("COUNTER PASS");
        $finish;
    end
endmodule