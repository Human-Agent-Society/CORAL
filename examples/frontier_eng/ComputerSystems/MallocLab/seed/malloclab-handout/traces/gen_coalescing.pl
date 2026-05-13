#!/usr/bin/perl
#!/usr/local/bin/perl

$out_filename = "coalescing.rep";
$blk_size = 4095;
$num_iters = 2400;

# Open output file
open OUTFILE, ">$out_filename" or die "Cannot create $out_filename\n";

# Calculate misc parameters
$blk_size2 = 2*$blk_size;
$suggested_heap_size = 2*$blk_size*$num_iters + 100;
$num_blocks = 3*$num_iters;
$num_ops = 6*$num_iters;

print OUTFILE "$suggested_heap_size\n";
print OUTFILE "$num_blocks\n";
print OUTFILE "$num_ops\n";
print OUTFILE "1\n";

for ($i = 0;  $i < $num_iters; $i += 1) {
    $blk1 = 3*$i;
    $blk2 = $blk1 + 1;
    $blk3 = $blk1 + 2;

    print OUTFILE "a $blk1 $blk_size\n";
    print OUTFILE "a $blk2 $blk_size\n";
    print OUTFILE "f $blk1\n";
    print OUTFILE "f $blk2\n";
    print OUTFILE "a $blk3 $blk_size2\n";
    print OUTFILE "f $blk3\n";
}

close OUTFILE;

