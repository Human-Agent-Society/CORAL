#!/usr/bin/perl
#!/usr/local/bin/perl

$out_filename = "binary.rep";
$blk_size1 = 64;
$blk_size2 = 512 - $blk_size1;
$num_iters = 2000;

# Open output file
open OUTFILE, ">$out_filename" or die "Cannot create $out_filename\n";

# Calculate misc parameters
$blk_size12 = $blk_size1 + $blk_size2;
$suggested_heap_size = ($blk_size1 + $blk_size2 + $blk_size12)*$num_iters + 100;
$num_blocks = 3*$num_iters;
$num_ops = 4*$num_iters;

print OUTFILE "$suggested_heap_size\n";
print OUTFILE "$num_blocks\n";
print OUTFILE "$num_ops\n";
print OUTFILE "1\n";

for ($i = 0;  $i < $num_iters; $i += 1) {
    $seq1 = 2*$i;
    $seq2 = 2*$i + 1;
    print OUTFILE "a $seq1 $blk_size1\n";
    print OUTFILE "a $seq2 $blk_size2\n";
}
for ($i = 0;  $i < $num_iters; $i += 1) {
    $fseq = 2*$i + 1;
    print OUTFILE "f $fseq\n";
}
for ($i = 0;  $i < $num_iters; $i += 1) {
    $aseq = 2*$num_iters + $i;
    print OUTFILE "a $aseq $blk_size12\n";
}

close OUTFILE;

