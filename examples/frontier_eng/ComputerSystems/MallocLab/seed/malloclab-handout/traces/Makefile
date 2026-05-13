
all: synthetic-traces balanced-traces check-balance

synthetic-traces:
	./gen_binary.pl
	./gen_binary2.pl
	./gen_coalescing.pl
	./gen_random.pl
	./gen_realloc.pl
	./gen_realloc2.pl

balanced-traces:
	./checktrace.pl < amptjp.rep > amptjp-bal.rep
	./checktrace.pl < binary.rep > binary-bal.rep
	./checktrace.pl < binary2.rep > binary2-bal.rep
	./checktrace.pl < cccp.rep > cccp-bal.rep
	./checktrace.pl < coalescing.rep > coalescing-bal.rep
	./checktrace.pl < cp-decl.rep > cp-decl-bal.rep
	./checktrace.pl < expr.rep > expr-bal.rep
	./checktrace.pl < realloc.rep > realloc-bal.rep
	./checktrace.pl < realloc2.rep > realloc2-bal.rep
	./checktrace.pl < random.rep > random-bal.rep
	./checktrace.pl < random2.rep > random2-bal.rep
	./checktrace.pl < short1.rep > short1-bal.rep
	./checktrace.pl < short2.rep > short2-bal.rep

check-balance:
	./checktrace.pl -s < amptjp-bal.rep
	./checktrace.pl -s < binary-bal.rep
	./checktrace.pl -s < binary2-bal.rep
	./checktrace.pl -s < cccp-bal.rep
	./checktrace.pl -s < coalescing-bal.rep
	./checktrace.pl -s < cp-decl-bal.rep
	./checktrace.pl -s < expr-bal.rep
	./checktrace.pl -s < realloc-bal.rep
	./checktrace.pl -s < realloc2-bal.rep
	./checktrace.pl -s < random-bal.rep
	./checktrace.pl -s < random2-bal.rep
	./checktrace.pl -s < short1-bal.rep
	./checktrace.pl -s < short2-bal.rep
clean:
	rm -f *~
