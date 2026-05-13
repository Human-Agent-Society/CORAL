#!/usr/bin/perl 
#!/usr/local/bin/perl 
use Getopt::Std;

#######################################################################
# checktrace - trace file consistency checker and balancer.  
#
# Copyright (c) 2002, R. Bryant and D. O'Hallaron, All rights reserved.
# May not be used, modified, or copied without permission.
#
# This script reads a Malloc Lab trace file, checks it for consistency,
# and outputs a balanced version by appending any necessary free requests.
#
#######################################################################
 
$| = 1; # autoflush output on every print statement

#
# void usage(void) - print help message and terminate
#
sub usage 
{
    printf STDERR "$_[0]\n";
    printf STDERR "Usage: $0 [-hs]\n";
    printf STDERR "Options:\n";
    printf STDERR "  -h          Print this message\n";
    printf STDERR "  -s          Emit only a brief summary\n";
    die "\n" ;
}

##############
# Main routine
##############

# 
# Parse and check the command line arguments
#
getopts('hs');
if ($opt_h) {
    usage("");
}
$summary = $opt_s;

# 
# HASH keeps a running tally of outstanding alloc/realloc 
# requests. When a free request is encountered, the corresponding 
# hash entry is deleted. When we are finished reading the trace,
# what is left are the unmatched alloc/realloc requests.
#
%HASH = (); 

# Read the trace header values
$heap_size = <STDIN>;
chomp($heap_size);

$num_blocks = <STDIN>;
chomp($num_blocks);

$old_num_ops = <STDIN>;
chomp($old_num_ops);

$weight = <STDIN>;
chomp($weight);

# 
# Find any allocate requests that don't have a matching free requests
#
$linenum = 4;
$requestnum = 0;
while ($line = <STDIN>) {
    chomp($line);
    $linenum++;

    ($cmd, $id, $size) = split(" ", $line);

    # ignore blank lines
    if (!$cmd) {
	next;
    }

    # save the line for output later
    $lines[$requestnum++] = $line;

    #ignore realloc requests, as long as they are preceeded by an alloc request
    if ($cmd eq "r") {
	if (!$HASH{$id}) {
	    die "$0: ERROR[$linenum]: realloc without previous alloc\n";
	}
	next;
    }

    if ($cmd eq "a" and $HASH{$id} eq "a") {
	die "$0: ERROR[$linenum]: allocate with no intervening free.\n";
    }

    if ($cmd eq "a" and $HASH{$id} eq "f") {
	die "$0: ERROR[$linenum]: reused ID $id.\n";
    }

    if ($cmd eq "f" and !exists($HASH{$id})) {
	die "$0: ERROR[$linenum]: freeing unallocated block.\n";
	next;
    }

    if ($cmd eq "f" and !$HASH{$id} eq "f") {
	die "$0: ERROR[$linenum]: freeing already freed block.\n";
	next;
    }
    
    if ($cmd eq "f") {
	delete $HASH{$id};
    }
    else {
	$HASH{$id} = $cmd;
    }
}

# 
# If called with -s argument , print a brief balance summary and exit
#
if ($summary) {
    if (!%HASH) {
	print "Balanced trace.\n";
    } 
    else {
	print "Unbalanced tree.\n";
    }
    exit;
}

#
# Output a balanced version of the trace
#
$new_ops = keys %HASH;
$new_num_ops = $old_num_ops + $new_ops;

print "$heap_size\n";
print "$num_blocks\n";
print "$new_num_ops\n";
print "$weight\n";

# print the old requests
foreach $item (@lines) {
    print "$item\n";
}

# print a set of free requests that will balance the trace
foreach $key (sort keys %HASH) {
    if ($HASH{$key} ne "a" and $HASH{$key} ne "r") {
	die "$0: ERROR: Invalid free request in residue.\n";
    }
    print "f $key\n";
}

exit;
