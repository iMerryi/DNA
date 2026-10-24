#include<iostream>
#include<string>
#include<vector>
#include<unordered_map>
#include<utility>
#include<cmath>
#include<ctime>
using namespace std;
string ans1; //原始DNA序列 
int fix;

unordered_map<char, double> stable =
{
	{'A', 1.0}, {'T', 1.0},
	{'C', 1.5}, {'G', 1.5},
	{'X', 1.8}, {'Y', 1.8},
};

pair<double, double> stable_scope;
double stable_need;
pair<double, double> CG_scope = { 0.4, 0.6 };
double CG_need = 0.5;
long long MAX_length = 10000;
int each_length_MAX = 10;
bool CG_check;
bool stable_check;

double stable_score(string s)  //碱基热稳定性系数
{
	double ans = 0.0;
	double cnt = 0;
	for (auto c : s)
	{
		auto it = stable.find(c);
		if (it != stable.end())
		{
			ans += it->second;
			cnt++;
		}
	}
	return ans / cnt;
}
void stable_standard()   //计算稳定性的合理范围和标准
{
	double stable_min = min({ stable['A'], stable['C'], stable['X'] });
	double stable_max = max({ stable['A'], stable['C'], stable['X'] });
	double span = stable_max - stable_min;
	stable_need = (stable_max + stable_min) / 2.0;
	stable_scope.first = stable_min + span * 0.3;
	stable_scope.second = stable_max - span * 0.3;
}


double CG_score(string s)   //CG含量
{
	int ans = 0;
	int n = s.length();
	for (char it : s)
	{
		if (it == 'C' || it == 'G') ans++;
	}
	return (double)ans / n;
}
string add(int x, int n)  //需要CG/AT 需要长度(不加人工碱基)
{
	if (n < 0) n = 2;
	string final_ans;
	string stand;
	string ans = "X";  //开头X结尾Y，用人工碱基做标记 
	if (x == 0)  stand = "CG";
	else if (x == 1) stand = "AT";
	while (n--)
	{
		int r = rand() % 2;
		ans = ans + stand[r];
		//if (n % 10 == 0) ans = ans + "YX";
	}
	return ans + 'Y';
}

void joint(string x)    //此处为了好检查，可能会做修改
{
	if (rand() % 2 == 1) ans1 = ans1 + x;
	else ans1 = x + ans1;
}

void CG_add(double current_CG)
{
	int n = ans1.length();
	if (current_CG < CG_scope.first)
	{
		//int need = n * (current_CG * (n + 2) - CG_need) / (1 - CG_need * n);
		double den = 1.0 - CG_need * n;
		if (fabs(den) < 1e-9) den = 1e-9;
		int need = (int)ceil(fabs(n * (current_CG * (n + 2) - CG_need) / den));
		if (need < 1) need = 1;
		else if (need > 3) need = 3;
		string x = add(0, need);
		joint(x);
	}
	else if (current_CG >= CG_scope.second)
	{
		//int need = (n * (CG_need * n - current_CG) + 2 * CG_need * n) / (-CG_need * n);
		double den = -CG_need * n;
		if (fabs(den) < 1e-9) den = 1e-9;
		int need = (int)ceil(fabs((n * (CG_need * n - current_CG) + 2 * CG_need * n) / den));
		if (need < 1) need = 1;
		else if (need > 3) need = 3;
		string x = add(1, need);
		joint(x);
	}
}

void stable_add(double current_stable)   //这个还没改，要算need
{
	int n = ans1.length();
	//double cur = (double)(current_stable * n + 2 * stable['X']) / (double)(n + 2);
	if (current_stable <= stable_scope.first)
	{
		//int need = ((n + 2) *( stable_need - cur_stable)) / (stable['G'] - stable_need);
		double den = stable['G'] - stable_need;
		if (fabs(den) < 1e-9) den = 1e-9;
		int need = (int)ceil(fabs(((n + 2) * (stable_need - current_stable)) / den));
		if (need < 1) need = 1;
		else if (need > 3) need = 3;
		string x = add(0, need);
		joint(x);
	}
	else if (current_stable >= stable_scope.second)
	{
		//int need = ((n + 2) * (stable_need - cur_stable)) / (stable['A'] - stable_need);
		double den = stable['A'] - stable_need;
		if (fabs(den) < 1e-9) den = 1e-9;
		int need = (int)ceil(fabs(((n + 2) * (stable_need - current_stable)) / den));
		if (need < 1) need = 1;
		else if (need > 3) need = 3;
		string x = add(1, need);
		joint(x);
	}
	//else joint("XY");
}

void main_add()
{
	int n = ans1.length();
	double current_CG = CG_score(ans1);
	double current_stable = stable_score(ans1);
	if (!CG_check && !stable_check)
	{
		double CG_departure = fabs(current_CG - CG_need) / CG_need;
		double stable_departure = fabs(current_stable - stable_need) / stable_need;
		if (CG_departure >= stable_departure)
		{
			CG_add(current_CG);
			//stable_add(stable_score(ans1));
		}
		else
		{
			stable_add(current_stable);
			//CG_add(CG_score(ans1));
		}
	}
	else if (!CG_check && stable_check)
	{
		CG_add(current_CG);
	}
	else if (CG_check && !stable_check)
	{
		stable_add(current_stable);
	}
}

bool main_check()
{
	double CG_num = CG_score(ans1);
	double stable_num = stable_score(ans1);
	CG_check = (CG_num >= CG_scope.first && CG_num <= CG_scope.second) ? true : false;
	stable_check = (stable_num >= stable_scope.first && stable_num <= stable_scope.second) ? true : false;
	if (CG_check && stable_check) return true;
	else return false;
}

string to_num(string s)
{
	string ans;
	for (auto c : s)
	{
		int ascii = c;
		for (int i = 7; i >= 0; i--) //每一个字母占8位（固定）
		{
			ans += ((ascii >> i) & 1) ? '1' : '0';
		}
	}
	if (ans.size() % 2 == 1)
	{
		fix = 1;
		ans += '0';
	}
	return ans;
}
void make_DNA(string s)
{
	ans1.clear();
	int n = s.size();
	for (int i = 0; i < n; i += 2)
	{
		string a = s.substr(i, 2);
		if (a == "11") ans1 = ans1 + 'A';
		else if (a == "01") ans1 = ans1 + 'T';
		else if (a == "10") ans1 = ans1 + 'C';
		else if (a == "00") ans1 = ans1 + 'G';
	}
}

string encryption(string a, string b)  //大 小
{
	string ans = "";
	int n = a.size();
	int m = b.size();
	for (int i = 0; i < n; i++)
	{
		int x = a[i] - '0';
		int y = b[i % m] - '0';
		string add = to_string(x ^ y);
		ans += add;
	}
	return ans;
}

int main()
{
	stable_standard();
	srand(time(0));
	string English;
	cout << "Please enter the symptom: ";
	getline(cin, English);  //对应初始碱基序列 
	cout << "Please enter the plaintext: ";
	string mingwen;
	getline(cin, mingwen);
	string num_layer = to_num(English);
	string mingwen_layer = to_num(mingwen);

	cout << "Binary layer of original data: " << num_layer << endl;
	cout << "Binary layer of encrypted data: " << mingwen_layer << endl;

	string final_binary = encryption(num_layer, mingwen_layer);
	cout << "final_binary: " << final_binary << "\n";

	make_DNA(final_binary);
	cout << "Input OK, start generating...\n";
	while (!main_check())
	{
		main_add();
		cout << "Repairing , please wait...\n";
		cout << "The length: " << ans1.size() << endl;
		cout << "GC Content: " << CG_score(ans1) << endl;
		cout << "Base Thermal Stability Coefficient: " << stable_score(ans1) << endl;
		if (ans1.length() >= MAX_length)
		{
			cout << "Cannot realize the sequence" << endl;
			return 0;
		}
	}

	//system("cls");

	cout << "=================================------------------Content Analysis------------------=================================" << endl;
	cout << "Ciphertext: " << mingwen << endl;
	cout << "GC Content: " << CG_score(ans1) << endl;
	cout << "Base Thermal Stability Coefficient: " << stable_score(ans1) << endl;
	cout << "Final DNA Sequence: " << ans1 << endl;
	cout << "Number of Padded Zeros: " << fix << endl;

	system("pause");
	return 0;
}