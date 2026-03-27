#include <bits/stdc++.h>
#include "testlib.h"
using namespace std;
 
const int MAX_LINE_NUM=1000;
 
char mask_tab[10][10];
unsigned int mask_ui[10];
 
void prepare(){
	for (int i=0;i<4;i++)
		for (int j=0;j<i;j++) mask_tab[i][j]=0xFF;
	for (int i=0;i<4;i++) mask_ui[i]=*((unsigned int*)mask_tab[i]);
}
 
int line_num;
int tp[MAX_LINE_NUM+50];
char A[MAX_LINE_NUM+50][10];
char B[MAX_LINE_NUM+50][10];
int lenA[MAX_LINE_NUM+50];
int lenB[MAX_LINE_NUM+50];
int dlen[MAX_LINE_NUM+50];
unsigned int pressA[MAX_LINE_NUM+50];
unsigned int maskA[MAX_LINE_NUM+50];
 
void read_program(){
	pattern tp1("[a-zA-Z0-9]{0,3}\\=[a-zA-Z0-9]{0,3}");
	pattern tp2("[a-zA-Z0-9]{0,3}\\=\\(return\\)[a-zA-Z0-9]{0,3}");
	while (!ouf.eof()){
		
		line_num++;
		
		string s = ouf.readString("[a-zA-Z0-9=()]{0,13}","program[i]");
		bool match_tp1=tp1.matches(s);
		bool match_tp2=tp2.matches(s);
		
		if (!match_tp1 && !match_tp2)
			quitf(_wa, "The %d - th line is an invalid instruction.",line_num);
		if (line_num>MAX_LINE_NUM)
			quitf(_wa, "Too much instructions.");
		
		int len=s.length();
		int pos1=0,pos2=0;
		pos1=s.find("=");
		if (match_tp1) pos2=pos1+1;
		else pos2=s.find(")")+1;
		
		if (match_tp1) tp[line_num]=0;
		else tp[line_num]=1; 
		
		strcpy(A[line_num],(s.substr(0,pos1)).c_str());
		strcpy(B[line_num],(s.substr(pos2,len-pos2)).c_str());
		lenA[line_num]=strlen(A[line_num]);
		lenB[line_num]=strlen(B[line_num]);
		dlen[line_num]=lenA[line_num]-lenB[line_num];
		
		pressA[line_num]=*((unsigned int*)A[line_num]);
		maskA[line_num]=mask_ui[lenA[line_num]];
	}
}
 
namespace RunProgram{
	char s[100050];
	char tmp[100050];
	char* pos[(1<<24)+50];
	int len=0, exe_cnt=0;
	int EXECUTE_CNT_MIN=0, EXECUTE_CNT_MAX=0;
	int EXECUTE_LENGTH_MIN=0, EXECUTE_LENGTH_MAX=0;
	void init(string &init_s){
		strcpy(s,init_s.c_str());
		len=init_s.length();
		EXECUTE_CNT_MIN=max(2*len*len,50);
		EXECUTE_CNT_MAX=EXECUTE_CNT_MIN*2;
		EXECUTE_LENGTH_MIN=2*len+10;
		EXECUTE_LENGTH_MAX=EXECUTE_LENGTH_MIN*2;
	}
	void run_program(int &T){
		/*
		cerr << s << endl;
		*/
		for (exe_cnt=0;;){
			for (char* ps=s+len;;ps--){
				unsigned int masks=*((unsigned int*)(ps));
				for (int j=1;j<4;j++){
					unsigned int m=masks&mask_ui[j];
					pos[m]=ps; 
				}
				if (ps==s) break;
			}
			pos[0]=s;
			char* ps=NULL;
			int i=1;
			for (;i<=line_num;i++){
				ps=pos[pressA[i]];
				if (ps!=NULL) break;
			}
			if (i==line_num+1) break;
			for (char* ps=s+len;;ps--){
				unsigned int masks=*((unsigned int*)(ps));
				for (int j=1;j<4;j++){
					unsigned int m=masks&mask_ui[j];
					pos[m]=NULL; 
				}
				if (ps==s) break;
			}
			if ((++exe_cnt)>EXECUTE_CNT_MAX)
				quitf(_wa, "Line %d .Instruction execution exceeded.",T);
			if (tp[i]==1){
				strcpy(s,B[i]);
				len=lenB[i];
				break;
			}
			int D=dlen[i];
			if (D>0){
				char* src=ps+lenA[i];
				char* dst=src-D;
				while((*dst++=*src++)!='\0');
			}
			else if (D<0){
				char* src=s+len;
				char* dst=src-D;
				for (;;){
					(*dst)=(*src);
					if (src==ps) break;
					dst--;
					src--;
				}
			}
			{
				char* pb=B[i];
				for (;(*pb);){
					*ps++=*pb++;
				}
			}
			len-=D;
			s[len]='\0';
			/*
			cerr << "-------" << endl;
			cerr << len << endl;
			cerr << s << endl;
			*/
			if (len>EXECUTE_LENGTH_MAX) quitf(_wa,"Line %d .string becomes too long!",T);
		}
	}
	
	double calcRatio(){
		double ratioCnt = min(1.0, max(0.0, 1.0 - (exe_cnt - EXECUTE_CNT_MIN) / EXECUTE_CNT_MIN));
		double ratioLen = min(1.0, max(0.0, 1.0 - (len - EXECUTE_LENGTH_MIN) / EXECUTE_LENGTH_MIN));
		return ratioCnt * ratioLen;
	}
}
 
string init_s[1100050];
string final_s[1100050];
int Tcase;
 
namespace test_gen{
	int Tid=0;
//	vector< pair<string,string> > ask;
	void add(string &A,string &B){
		char tmp=(A.find(B)!=string::npos)+'0';
		string str;
		str.push_back(tmp);
	//	ask.emplace_back(A+'S'+B,str);
		Tcase++;
		init_s[Tcase]=A+'S'+B;
		final_s[Tcase]=str;
	}
	
	vector<int> tab{0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20};
	map<int,int> dict;
	
	int pw3[20];
	string lst[100050];
	int lst_sz;
	vector<pair<int,int> > lst_id;
	void prepare(){
		for (int i=0;i<(int)tab.size();i++) dict[tab[i]]=i;
		pw3[0]=1;
		for (int i=1;i<=15;i++) pw3[i]=pw3[i-1]*3;
		for (int len=1;len<=6;len++){
			for (int i=0;i<pw3[len];i++){
				string &A=lst[++lst_sz];
				for (int tmp=i,k=0;k<len;k++,tmp/=3) A.push_back('a'+tmp%3);
			}
		}
		for (int i=1;i<=lst_sz;i++)
			for (int j=1;j<=lst_sz;j++) lst_id.emplace_back(i,j);
	}
	
	void work(int op,unsigned long long data_seed){
		mt19937 rng(data_seed);
		vector< function<void()> > vf;
		
		vf.push_back(
			[&](){
				
			}
		);
		vf.push_back(
			[&](){
				{
					string A="abcabbabc";
					string B="cabb";
					add(A,B);
				}
				{
					string A="abcabbabc";
					string B="cbabb";
					add(A,B);
				}
				{
					string A="aabcabacac";
					string B="abb";
					add(A,B);
				}
				{
					string A="aabcabacac";
					string B="baca";
					add(A,B);
				}
			}
		);
		vf.push_back(
			[&](){
				int Tcase=100;
				for (int T=1;T<=Tcase;T++){
					string A;
					for (int i=1;i<=10;i++) A.push_back(rng()%3+'a');
					
					int expected_substr=rng()%10;
					
					int l=rng()%10;
					int r=rng()%10;
					if (l>r) swap(l,r);
					string B=A.substr(l,r-l+1);
					int len=r-l+1;
					
					if (expected_substr<6){
						int pos=rng()%len;
						B[pos]=(B[pos]-'a'+1)%3+'a';
					}
					
					add(A,B);
				}
			}
		);
		vf.push_back(
			[&](){
				int Tcase=100;
				for (int T=1;T<=Tcase;T++){
					string C;
					for (int i=1;i<=10;i++) C.push_back(rng()%3+'a');
					
					int l=rng()%10;
					int r=rng()%10;
					string A=C.substr(l,10-l);
					string B=C.substr(r,10-r);
					
					add(A,B);
				}
			}
		);
		vf.push_back(
			[&](){
				int Tcase=100;
				for (int T=1;T<=Tcase;T++){
					string C;
					for (int i=1;i<=10;i++) C.push_back(rng()%3+'a');
					
					int l=rng()%10;
					int r=rng()%10;
					string A=C.substr(0,l+1);
					string B=C.substr(0,r+1);
					
					add(A,B);
				}
			}
		);
		vf.push_back(
			[&](){
				{
					string A(99,'c');
					A.push_back('a');
					string B(9,'c');
					B.push_back('b');
					add(A,B);
				}
				{
					string A(99,'c');
					A.push_back('a');
					string B(9,'c');
					B.push_back('a');
					add(A,B);
				}
			}
		);
		vf.push_back(
			[&](){
				{
					string A(599,'c');
					A.push_back('a');
					string B(99,'c');
					B.push_back('b');
					add(A,B);
				}
				{
					string A;
					for (int i=0;i<500;i++) A.push_back(rng()%3+'a');
					string B=A.substr(125,250);
					add(A,B);
				}
			}
		);
		
		{
			int B=10;
			int sz=lst_id.size();
			int Bsz=(sz+B-1)/B;
			for (int i=0;i<B;i++){
				int l=Bsz*i;
				int r=min(Bsz*(i+1),sz);
				vf.push_back(
					[&,l,r](){
						for (int k=l;k<r;k++){
							add(lst[lst_id[k].first],lst[lst_id[k].second]);
						}
					}
				);
			}
		}
		
		
		(vf[op])();
	}
	
	void gao(){
		ios_base::sync_with_stdio(false);
		{
			prepare();
		}
		{	
			int data_id=dict[Tid%100];
			unsigned long long data_seed=Tid/100;
			work(data_id,data_seed);
		}
	}
}
void check_Tid(){
	test_gen::Tid=inf.readInteger();
	if (test_gen::Tid%100==0) quitf(_ok,"Test 0.");
}
void read_test(){
	test_gen::gao();
	/*
	long long cnt=0;
	for (int i=1;i<=Tcase;i++){
		long long L=init_s[i].length();
		cnt=cnt+max(2*L*L,50LL)*max(2*L+10,100LL);
	}
	cerr << cnt << endl;
	*/
	/*
	freopen("oops.txt","w",stderr);
	cerr << Tcase << "\n";
	for (int i=1;i<=Tcase;i++) cerr << init_s[i] << "\n" << final_s[i] << "\n";
	*/
}
void validate_test(){
	pattern tp1("[abcS]{3,1000}");
	pattern tp2("[abc]{1,1000}S[abc]{1,1000}");
	for (int T=1;T<=Tcase;T++){
		bool match_tp1=tp1.matches(init_s[T]);
		bool match_tp2=tp2.matches(init_s[T]);
		if (match_tp1 && match_tp2) continue;
		quitf(_fail, "Test %d INVALID. Please fix the data !!!",T);
	}
}
void test_program(){
	double ratio = 0;
	for (int T=1;T<=Tcase;T++){
		RunProgram::init(init_s[T]);
		RunProgram::run_program(T);
		if (strcmp(RunProgram::s,final_s[T].c_str())!=0){
			quitf(_wa, "WA on Test case %d. %s %s",T,init_s[T].c_str(),final_s[T].c_str());
		}
		ratio = RunProgram::calcRatio();
	}
	char mes[30];
	sprintf(mes, "Ratio: %lf", ratio);
	quitp(ratio, "%s", mes);
}
int main(int argc, char * argv[]){
	registerTestlibCmd(argc, argv);
	prepare();
	read_program();
	check_Tid();
	read_test();
	validate_test();
	test_program();
	return 0;
}
