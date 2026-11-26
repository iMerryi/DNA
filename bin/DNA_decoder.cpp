#include<iostream>
#include<string>
#include<stack>
using namespace std;
string order, key;
void remove()
{
	stack<int> x, y;
	int num = order.size();
	for (int i = 0; i < num; i++)
	{
		if (order[i] == 'X') x.push(i);
		else if (order[i] == 'Y') y.push(i);
	}
	if (x.size() != y.size())
	{
		cout << "Error: There is a problem with the ciphertext input.\n";
		return;
	}
	while (!x.empty() && !y.empty())
	{
		int a = x.top(); x.pop();
		int b = y.top(); y.pop();
		order.erase(order.begin() + a, order.begin() + b);
	}
}

string key_to_num(string s)
{
	string ans;
	for (auto c : s)
	{
		int ascii = c;
		for (int i = 7; i >= 0; i--)
		{
			ans += ((ascii >> i) & 1) ? '1' : '0';
		}
	}
	if (ans.size() % 2 == 1)
	{
		ans += '0';
	}
	return ans;
}

string order_to_num(string s)
{
	string ans1;
	for (auto a : s)
	{
		if (a == 'A') ans1 += "11";
		else if (a == 'T') ans1 += "01";
		else if (a == 'C') ans1 += "10";
		else if (a == 'G') ans1 += "00";
	}
	return ans1;
}

string jiemi_num()
{
	string ans = "";
	string key_num = key_to_num(key);
	string order_num = order_to_num(order);
	int a = key_num.size(), b = order_num.size();
	for (int i = 0; i < b; i++)
	{
		int x = key_num[i % a] - '0', y = order_num[i] - '0';
		int z = x ^ y;
		ans += z + '0';
	}
	return ans;
}
char restore(string s)
{
	int num = 0;
	for (auto c : s)
	{
		int it = c - '0';
		num = num * 2 + it;
	}
	//cout << num << "\n";
	return static_cast<char>(num);
}
void fuyuan(string x)
{
	string ans = "";
	if (x.size() % 8 != 0)
	{
		cout << "The number is NOT an even number.\n";
		return;
	}
	int num = x.size() / 8;
	for (int i = 0; i < num; i++)
	{
		ans += restore(x.substr(i * 8, 8));
	}
	cout << "========--------------[ Decryption Result ]--------------=======\n";
	cout << ans << "\n";
	return;
}
int main()
{
	cout << "Please enter the ciphertext: ";
	getline(cin, order);
	cout << "Please enter the key: ";
	getline(cin, key);
	remove();
	string ans_num = jiemi_num();
	fuyuan(ans_num);
	return 0;
}