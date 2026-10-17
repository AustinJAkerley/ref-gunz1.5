#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>
struct sqlite3;

namespace competitive {
constexpr int startingElo=1000, kFactor=32, maxLevel=99;
enum class Rank : int { Iron, Bronze, Silver, Gold, Top10, First };
inline Rank rank(int elo,int place) {
    if(place==1)return Rank::First;
    if(place>=2&&place<=10)return Rank::Top10;
    return elo<1000?Rank::Iron:elo<1200?Rank::Bronze:elo<1500?Rank::Silver:Rank::Gold;
}
inline const char* label(int value) {
    static const char* names[]={"Iron","Bronze","Silver","Gold","Top 10","Rank 1"};
    return value>=0&&value<6?names[value]:"--";
}
inline int delta(int winner,int loser) {
    double expected=1.0/(1.0+std::pow(10.0,std::max(-20.0,std::min(20.0,(loser-winner)/400.0))));
    return std::min(loser,std::max(1,int(std::floor(kFactor*(1-expected)+.5))));
}
struct Rating {int cid=0,elo=startingElo,wins=0,losses=0,place=0;};
struct Result {bool applied=false;int change=0;};
void initialize(sqlite3* db);
void grant(sqlite3* db,int cid,int sex);
Result record(sqlite3* db,const std::string& event,int winner,int loser,const char* reason);
std::vector<Rating> ladder(sqlite3* db);
}