// dna_match.cpp - DNA 纠错 DP 细筛工具
// 编译: g++ -std=c++11 -O2 -o dna_match.exe dna_match.cpp
// 协议见: docs/modules/解码纠错_AI粗配与DP细筛设计.md §5.1

#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <cmath>
#include <iomanip>

using namespace std;

// 标准 Levenshtein 距离：替换/插入/删除代价均为 1
int levenshtein(const string& a, const string& b) {
    int n = a.size(), m = b.size();
    vector<vector<int>> dp(n + 1, vector<int>(m + 1));
    
    for (int i = 0; i <= n; i++) dp[i][0] = i;
    for (int j = 0; j <= m; j++) dp[0][j] = j;
    
    for (int i = 1; i <= n; i++) {
        for (int j = 1; j <= m; j++) {
            int cost = (a[i-1] == b[j-1]) ? 0 : 1;
            dp[i][j] = min({
                dp[i-1][j] + 1,      // 删除
                dp[i][j-1] + 1,      // 插入
                dp[i-1][j-1] + cost  // 替换
            });
        }
    }
    return dp[n][m];
}

struct Result {
    int index;
    int dist;
    double score;
};

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    
    string line;
    
    // 读目标词: "T <count>"
    getline(cin, line);
    if (line.empty() || line[0] != 'T') return 1;
    int t_count = stoi(line.substr(2));
    if (t_count != 1) return 1;  // 当前只支持单目标词
    
    string target;
    getline(cin, target);
    
    // 读候选: "N <count>"
    getline(cin, line);
    if (line.empty() || line[0] != 'N') return 1;
    int n_count = stoi(line.substr(2));
    
    vector<string> candidates(n_count);
    for (int i = 0; i < n_count; i++) {
        getline(cin, candidates[i]);
    }
    
    // 计算距离和相似度
    vector<Result> results;
    for (int i = 0; i < n_count; i++) {
        int dist = levenshtein(target, candidates[i]);
        int max_len = max(target.size(), candidates[i].size());
        double score = (max_len == 0) ? 1.0 : 1.0 - (double)dist / max_len;
        results.push_back({i, dist, score});
    }
    
    // 按距离升序，同距离按候选索引升序
    sort(results.begin(), results.end(), [](const Result& a, const Result& b) {
        if (a.dist != b.dist) return a.dist < b.dist;
        return a.index < b.index;
    });
    
    // 输出: index dist score
    cout << fixed << setprecision(3);
    for (const auto& r : results) {
        cout << r.index << " " << r.dist << " " << r.score << "\n";
    }
    
    return 0;
}
