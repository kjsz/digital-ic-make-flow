// 自写最小示例，仅用于说明 filelist、sim 和综合入口。
module counter(input logic clk, input logic rst_n, output logic [3:0] count);
    always_ff @(posedge clk or negedge rst_n)
        if (!rst_n) count <= 4'd0;
        else count <= count + 4'd1;
endmodule